"""FastAPI web UI for renderdiff."""

from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..fetcher import create_client
from ..indexation import GoogleIndexChecker
from ..input import resolve_urls
from ..models import IndexReport, IndexResult, IndexStatus, RunReport, Severity, UrlReport
from ..pipeline import process_url
from ..renderer import HeadlessRenderer


# ---------------------------------------------------------------------------
# Request / state models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=100)
    sitemap: str | None = None
    concurrency: int = Field(default=3, ge=1, le=10)
    delay: float = Field(default=1.0, ge=0, le=10)
    limit: int | None = Field(default=None, ge=1, le=500)


class ScanCreated(BaseModel):
    run_id: str
    total_urls: int


class ScanStatus(BaseModel):
    run_id: str
    status: str  # "running" | "complete" | "error"
    total_urls: int
    completed_urls: int
    report: RunReport | None = None


class IndexCheckRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=100)
    sitemap: str | None = None
    delay: float = Field(default=5.0, ge=1, le=30)
    limit: int | None = Field(default=None, ge=1, le=500)


class IndexCheckCreated(BaseModel):
    run_id: str
    total_urls: int


class IndexCheckStatus(BaseModel):
    run_id: str
    status: str  # "running" | "complete" | "error"
    total_urls: int
    completed_urls: int
    report: IndexReport | None = None


@dataclass
class _ScanState:
    run_id: str
    urls: list[str]
    concurrency: int
    delay: float
    status: str = "running"
    completed: int = 0
    queue: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue)
    url_reports: list[UrlReport] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    screenshot_dir: str = ""
    task: asyncio.Task | None = field(default=None, repr=False)  # type: ignore[type-arg]


@dataclass
class _IndexCheckState:
    run_id: str
    urls: list[str]
    delay: float
    status: str = "running"
    completed: int = 0
    queue: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue)
    results: list[IndexResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    screenshot_dir: str = ""
    task: asyncio.Task | None = field(default=None, repr=False)  # type: ignore[type-arg]


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_scans: dict[str, _ScanState] = {}
_index_checks: dict[str, _IndexCheckState] = {}

_STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="renderdiff", docs_url="/docs")

    # -- Serve SPA ----------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html_path = _STATIC_DIR / "index.html"
        return HTMLResponse(html_path.read_text())

    # -- Start scan ---------------------------------------------------------

    @app.post("/api/scan", response_model=ScanCreated)
    async def start_scan(req: ScanRequest) -> ScanCreated:
        # Resolve URLs
        urls = await resolve_urls(
            url=None,
            sitemap_url=req.sitemap,
            limit=req.limit,
        )
        # Add explicit URLs
        for u in req.urls:
            u = u.strip()
            if u:
                urls.append(u)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        urls = unique

        if not urls:
            raise HTTPException(status_code=400, detail="No URLs provided")

        run_id = uuid.uuid4().hex[:12]
        screenshot_dir = tempfile.mkdtemp(prefix=f"renderdiff-{run_id}-")

        state = _ScanState(
            run_id=run_id,
            urls=urls,
            concurrency=req.concurrency,
            delay=req.delay,
            started_at=datetime.now(timezone.utc).isoformat(),
            screenshot_dir=screenshot_dir,
        )
        _scans[run_id] = state
        state.task = asyncio.create_task(_run_scan(state))

        return ScanCreated(run_id=run_id, total_urls=len(urls))

    # -- SSE stream ---------------------------------------------------------

    @app.get("/api/scan/{run_id}/stream")
    async def stream_scan(run_id: str) -> StreamingResponse:
        state = _scans.get(run_id)
        if not state:
            raise HTTPException(status_code=404, detail="Scan not found")

        return StreamingResponse(
            _sse_generator(state),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # -- Get results --------------------------------------------------------

    @app.get("/api/scan/{run_id}")
    async def get_scan(run_id: str) -> ScanStatus:
        state = _scans.get(run_id)
        if not state:
            raise HTTPException(status_code=404, detail="Scan not found")

        report = _build_report(state) if state.status == "complete" else None
        return ScanStatus(
            run_id=state.run_id,
            status=state.status,
            total_urls=len(state.urls),
            completed_urls=state.completed,
            report=report,
        )

    # -- Serve screenshot ---------------------------------------------------

    @app.get("/api/scan/{run_id}/screenshot/{filename}")
    async def get_screenshot(run_id: str, filename: str) -> FileResponse:
        state = _scans.get(run_id)
        if not state:
            raise HTTPException(status_code=404, detail="Scan not found")
        file_path = Path(state.screenshot_dir) / filename
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Screenshot not found")
        return FileResponse(file_path, media_type="image/png")

    # -- Start index check ---------------------------------------------------

    @app.post("/api/index-check", response_model=IndexCheckCreated)
    async def start_index_check(req: IndexCheckRequest) -> IndexCheckCreated:
        urls = await resolve_urls(
            url=None,
            sitemap_url=req.sitemap,
            limit=req.limit,
        )
        for u in req.urls:
            u = u.strip()
            if u:
                urls.append(u)
        seen: set[str] = set()
        unique: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        urls = unique

        if not urls:
            raise HTTPException(status_code=400, detail="No URLs provided")

        run_id = uuid.uuid4().hex[:12]
        screenshot_dir = tempfile.mkdtemp(prefix=f"renderdiff-idx-{run_id}-")

        state = _IndexCheckState(
            run_id=run_id,
            urls=urls,
            delay=req.delay,
            started_at=datetime.now(timezone.utc).isoformat(),
            screenshot_dir=screenshot_dir,
        )
        _index_checks[run_id] = state
        state.task = asyncio.create_task(_run_index_check(state))

        return IndexCheckCreated(run_id=run_id, total_urls=len(urls))

    # -- Index check SSE stream ---------------------------------------------

    @app.get("/api/index-check/{run_id}/stream")
    async def stream_index_check(run_id: str) -> StreamingResponse:
        state = _index_checks.get(run_id)
        if not state:
            raise HTTPException(status_code=404, detail="Index check not found")
        return StreamingResponse(
            _sse_generator(state),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # -- Index check status -------------------------------------------------

    @app.get("/api/index-check/{run_id}")
    async def get_index_check(run_id: str) -> IndexCheckStatus:
        state = _index_checks.get(run_id)
        if not state:
            raise HTTPException(status_code=404, detail="Index check not found")
        report = _build_index_report(state) if state.status == "complete" else None
        return IndexCheckStatus(
            run_id=state.run_id,
            status=state.status,
            total_urls=len(state.urls),
            completed_urls=state.completed,
            report=report,
        )

    # -- Index check screenshot ---------------------------------------------

    @app.get("/api/index-check/{run_id}/screenshot/{filename}")
    async def get_index_screenshot(run_id: str, filename: str) -> FileResponse:
        state = _index_checks.get(run_id)
        if not state:
            raise HTTPException(status_code=404, detail="Index check not found")
        file_path = Path(state.screenshot_dir) / filename
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Screenshot not found")
        return FileResponse(file_path, media_type="image/png")

    return app


# ---------------------------------------------------------------------------
# Scan orchestration
# ---------------------------------------------------------------------------

async def _run_scan(state: _ScanState) -> None:
    """Background task that processes all URLs and pushes SSE events."""
    semaphore = asyncio.Semaphore(state.concurrency)
    client = create_client()

    try:
        async with client, HeadlessRenderer(screenshot_dir=state.screenshot_dir) as renderer:
            tasks = [
                _process_and_emit(url, idx, client, renderer, semaphore, state)
                for idx, url in enumerate(state.urls)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        state.status = "error"
        event = _sse_event("error", {"message": str(exc)})
        await state.queue.put(event)
        await state.queue.put(None)
        return

    state.finished_at = datetime.now(timezone.utc).isoformat()
    state.status = "complete"

    report = _build_report(state)
    event = _sse_event("scan_complete", report.model_dump(mode="json"))
    await state.queue.put(event)
    await state.queue.put(None)  # sentinel


async def _process_and_emit(
    url: str,
    index: int,
    client: object,
    renderer: HeadlessRenderer,
    semaphore: asyncio.Semaphore,
    state: _ScanState,
) -> None:
    """Process one URL and push events to the SSE queue."""
    # Notify start
    await state.queue.put(_sse_event("url_start", {"url": url, "index": index}))

    try:
        report = await process_url(url, client, renderer, semaphore, state.delay)
    except Exception as exc:
        report = UrlReport(
            url=url,
            timestamp=datetime.now(timezone.utc).isoformat(),
            skipped=True,
            skip_reason=str(exc),
        )

    # Strip large HTML fields to save memory
    if report.fetch:
        report.fetch.html = ""
    if report.render:
        report.render.rendered_html = ""

    # Rewrite screenshot_path to a relative filename for the API
    if report.render and report.render.screenshot_path:
        report.render.screenshot_path = Path(report.render.screenshot_path).name

    state.url_reports.append(report)
    state.completed += 1

    await state.queue.put(_sse_event("url_done", report.model_dump(mode="json")))


# ---------------------------------------------------------------------------
# Index check orchestration
# ---------------------------------------------------------------------------

async def _run_index_check(state: _IndexCheckState) -> None:
    """Background task that checks indexation for all URLs and pushes SSE events."""
    try:
        async with GoogleIndexChecker(
            delay=state.delay,
            screenshot_dir=state.screenshot_dir,
        ) as checker:
            for i, url in enumerate(state.urls):
                await state.queue.put(
                    _sse_event("url_start", {"url": url, "index": i})
                )

                result = await checker.check_url(url)

                # Rewrite screenshot_path to just the filename for the API
                if result.screenshot_path:
                    result.screenshot_path = Path(result.screenshot_path).name

                state.results.append(result)
                state.completed += 1

                await state.queue.put(
                    _sse_event("url_done", result.model_dump(mode="json"))
                )

                # Politeness delay (skip after last URL)
                if i < len(state.urls) - 1:
                    await asyncio.sleep(state.delay)

    except Exception as exc:
        state.status = "error"
        await state.queue.put(_sse_event("error", {"message": str(exc)}))
        await state.queue.put(None)
        return

    state.finished_at = datetime.now(timezone.utc).isoformat()
    state.status = "complete"

    report = _build_index_report(state)
    await state.queue.put(
        _sse_event("check_complete", report.model_dump(mode="json"))
    )
    await state.queue.put(None)  # sentinel


def _build_index_report(state: _IndexCheckState) -> IndexReport:
    results = state.results
    return IndexReport(
        run_id=state.run_id,
        started_at=state.started_at,
        finished_at=state.finished_at,
        total_urls=len(state.urls),
        indexed=sum(1 for r in results if r.status == IndexStatus.INDEXED),
        not_indexed=sum(1 for r in results if r.status == IndexStatus.NOT_INDEXED),
        blocked=sum(1 for r in results if r.status == IndexStatus.BLOCKED),
        errors=sum(1 for r in results if r.status == IndexStatus.ERROR),
        results=results,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_report(state: _ScanState) -> RunReport:
    reports = state.url_reports
    return RunReport(
        run_id=state.run_id,
        started_at=state.started_at,
        finished_at=state.finished_at,
        total_urls=len(state.urls),
        passed=sum(1 for r in reports if r.overall_status == "pass" and not r.skipped),
        warned=sum(1 for r in reports if r.overall_status == "warn"),
        failed=sum(1 for r in reports if r.overall_status == "fail"),
        skipped=sum(1 for r in reports if r.skipped),
        urls=reports,
    )


def _sse_event(event_type: str, data: object) -> str:
    payload = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _sse_generator(state: _ScanState | _IndexCheckState) -> AsyncGenerator[str, None]:
    """Yield SSE events from a state's queue."""
    while True:
        msg = await state.queue.get()
        if msg is None:
            break
        yield msg



# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the web UI server (used by renderdiff-web script entry)."""
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
