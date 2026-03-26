"""Shared test HTML fixtures."""

SAMPLE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Test Page Title</title>
    <meta name="description" content="Test description for SEO">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://example.com/page">
    <link rel="alternate" hreflang="en" href="https://example.com/en/page">
    <link rel="alternate" hreflang="es" href="https://example.com/es/page">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Test Page"
    }
    </script>
</head>
<body>
    <h1>Main Heading</h1>
    <h2>Sub Heading One</h2>
    <h2>Sub Heading Two</h2>
    <p>This is some visible text content on the page for word counting.</p>
    <a href="/about">About Us</a>
    <a href="https://external.com/link" rel="nofollow">External Link</a>
    <img src="/images/photo.jpg" alt="A photo" loading="lazy">
    <img src="https://cdn.example.com/banner.png" alt="Banner">
</body>
</html>
"""

SAMPLE_HTML_RENDERED = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Test Page Title - Updated by JS</title>
    <meta name="description" content="Test description for SEO">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://example.com/page">
    <link rel="alternate" hreflang="en" href="https://example.com/en/page">
    <link rel="alternate" hreflang="es" href="https://example.com/es/page">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Test Page"
    }
    </script>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": []
    }
    </script>
</head>
<body>
    <h1>Main Heading</h1>
    <h2>Sub Heading One</h2>
    <h2>Sub Heading Two</h2>
    <h2>Dynamic Sub Heading</h2>
    <p>This is some visible text content on the page for word counting.</p>
    <p>Extra JS-injected paragraph with additional words for the page.</p>
    <a href="/about">About Us</a>
    <a href="https://external.com/link" rel="nofollow">External Link</a>
    <a href="/products">Products</a>
    <img src="/images/photo.jpg" alt="A photo" loading="lazy">
    <img src="https://cdn.example.com/banner.png" alt="Banner">
    <img src="/images/lazy1.jpg" alt="Lazy image" loading="lazy">
    <img src="/images/lazy2.jpg" alt="Another lazy" loading="lazy">
</body>
</html>
"""
