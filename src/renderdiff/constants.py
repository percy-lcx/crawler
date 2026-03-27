"""Configuration constants for renderdiff."""

from __future__ import annotations

GENERIC_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

MOBILE_GOOGLEBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36 "
    "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

VIEWPORT_WIDTH = 412
VIEWPORT_HEIGHT = 732
SETTLE_SECONDS = 2
DEFAULT_TIMEOUT_MS = 30_000
NAVIGATION_TIMEOUT_MS = 10_000
DEFAULT_CONCURRENCY = 3
DEFAULT_DELAY_S = 1.0

HTML_SIZE_LIMIT_BYTES = 2 * 1024 * 1024  # 2 MB

WORD_COUNT_THRESHOLD_PCT = 20
LINK_COUNT_THRESHOLD_PCT = 10
IMAGE_COUNT_THRESHOLD_PCT = 10

CLOUDFLARE_MARKERS = [
    "cf-browser-verification",
    "cf-challenge-running",
    "Checking your browser",
    "cf_clearance",
    "challenge-platform",
]

FONT_EXTENSIONS = ("woff", "woff2", "ttf", "otf", "eot")

# Indexation checker
DEFAULT_INDEX_DELAY_S = 5.0
GOOGLE_SEARCH_URL = "https://www.google.com/search"
INDEX_NAVIGATION_TIMEOUT_MS = 15_000
INDEX_SETTLE_SECONDS = 2
