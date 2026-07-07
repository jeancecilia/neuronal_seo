"""
Test Playwright JS rendering with real HTTP server and JS-injected content.
Pages are served via a local HTTP server to test actual browser rendering.
"""

import asyncio
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models import Project, Page
from sqlalchemy import select


# ---------------------------------------------------------------------------
# In-memory HTTP server serving a JS-heavy page
# ---------------------------------------------------------------------------
JS_PAGE_HTML = """<!DOCTYPE html>
<html><head><title>Loading...</title></head>
<body>
  <div id="app">Loading...</div>
  <script>
    // Simulate JS framework rendering
    document.getElementById('app').innerHTML = '<h1>JS Rendered Heading</h1><h2>Service Overview</h2><h2>Pricing Plans</h2><h2>FAQ</h2><p>' + 'This content was rendered by JavaScript. ' + 'It contains useful information that static crawlers cannot see. ' + 'We offer professional services for your business needs. ' + 'Contact us today for a free consultation. ' + 'Our team has over 10 years of experience. '.repeat(20) + '</p>';
    document.title = 'JS Rendered Page - Full Content';
    var meta = document.createElement('meta');
    meta.name = 'description';
    meta.content = 'JS-rendered meta description with service keywords';
    document.head.appendChild(meta);
    var link = document.createElement('link');
    link.rel = 'canonical';
    link.href = 'https://js-test.local/canonical-url';
    document.head.appendChild(link);
    var a1 = document.createElement('a'); a1.href='/services'; a1.textContent='Services'; document.body.appendChild(a1);
    var a2 = document.createElement('a'); a2.href='/pricing'; a2.textContent='Pricing'; document.body.appendChild(a2);
  </script>
</body></html>"""


class JSPageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(JS_PAGE_HTML.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress logs


@pytest.fixture(scope="module")
def js_server():
    """Start a local HTTP server serving JS-rendered pages.
    Binds to 0.0.0.0 so it's accessible from Playwright subprocess."""
    server = HTTPServer(("0.0.0.0", 0), JSPageHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()


# ---------------------------------------------------------------------------
# Real Playwright crawl tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_playwright_crawls_js_page(db_session, js_server):
    """
    Real test: start an HTTP server with JS-injected content,
    crawl it with Playwright, and verify all JS-rendered data is extracted.
    """
    from app.services.crawler import CrawlerService

    project = Project(
        domain=f"http://localhost:{js_server}",
        target_country="DE",
        target_language="de",
    )
    db_session.add(project)
    await db_session.flush()

    crawler = CrawlerService(db_session)
    crawler._is_crawlable = MagicMock(return_value=True)
    crawler._is_valid_url = MagicMock(return_value=True)
    crawler.max_pages = 1

    # Crawl with JS rendering enabled
    result = await crawler.crawl_site(project, max_pages=1, use_js=True)

    assert result["pages_crawled"] > 0, "Should crawl at least one page"

    # Verify page was saved
    q = await db_session.execute(
        select(Page).where(Page.project_id == project.id)
    )
    pages = q.scalars().all()
    assert len(pages) > 0, "Page should be saved"

    page = pages[0]

    # Check JS-rendered content
    assert page.title == "JS Rendered Page - Full Content", f"Expected JS-rendered title, got: {page.title}"
    assert page.h1 == "JS Rendered Heading", f"Expected JS-rendered h1, got: {page.h1}"
    assert "Service Overview" in (page.h2 or []), "h2 'Service Overview' should be extracted"
    assert "Pricing Plans" in (page.h2 or []), "h2 'Pricing Plans' should be extracted"
    assert "FAQ" in (page.h2 or []), "h2 'FAQ' should be extracted"
    assert page.meta_description == "JS-rendered meta description with service keywords"
    assert page.canonical_url == "https://js-test.local/canonical-url"
    assert page.word_count >= 50, f"Expected rich JS content, got only {page.word_count} words"
    assert "professional services" in (page.content or "").lower(), "Content should include JS-rendered text"
    assert page.render_mode == "playwright", f"Render mode should be playwright, got {page.render_mode}"

    # Check internal links extracted from JS
    assert len(page.internal_links or []) >= 2, "Should extract JS-generated links"


@pytest.mark.asyncio
async def test_static_crawler_misses_js_content(db_session, js_server):
    """
    Verify that the static httpx crawler gets weak content from JS pages,
    confirming that Playwright fallback is necessary.
    """
    from app.services.crawler import CrawlerService

    project = Project(
        domain=f"http://localhost:{js_server}",
        target_country="DE",
        target_language="de",
    )
    db_session.add(project)
    await db_session.flush()

    crawler = CrawlerService(db_session)
    crawler._is_crawlable = MagicMock(return_value=True)
    crawler._is_valid_url = MagicMock(return_value=True)
    crawler.max_pages = 1

    # Crawl WITHOUT JS rendering
    result = await crawler.crawl_site(project, max_pages=1, use_js=False)

    assert result["pages_crawled"] > 0

    q = await db_session.execute(
        select(Page).where(Page.project_id == project.id)
    )
    pages = q.scalars().all()
    assert len(pages) > 0

    page = pages[0]
    # Static crawler should see "Loading..." not the JS content
    assert page.render_mode == "http"
    assert page.title == "Loading..." or page.word_count < 20, \
        "Static crawler should get weak/placeholder content from JS pages"


# ---------------------------------------------------------------------------
# Mock-based Playwright fallback tests (kept for fast unit validation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_playwright_fallback_on_weak_content(db_session):
    """When httpx returns content with < 50 words and use_js=True,
    the crawler should fall back to Playwright."""
    from app.services.crawler import CrawlerService

    project = Project(domain="js-heavy.local", target_country="DE", target_language="de")
    db_session.add(project)
    await db_session.flush()

    weak_page = {
        "url": "https://js-heavy.local/", "status_code": 200,
        "title": "JS App", "h1": "Loading...", "h2": [], "h3": [],
        "content": "Loading... Please wait.", "word_count": 3,
        "canonical_url": None, "indexable": True, "internal_links": [],
        "external_links": [], "images_alt_text": [], "schema_markup": None,
        "page_type": "landing_page", "language": "en",
    }

    playwright_page = {
        "url": "https://js-heavy.local/", "status_code": 200,
        "title": "Full Rendered Page", "h1": "Welcome to Our Service",
        "h2": ["Services", "Pricing", "Contact"], "h3": [],
        "content": "This is the fully rendered content after JavaScript execution. " * 50,
        "word_count": 500, "canonical_url": None, "indexable": True,
        "internal_links": ["/services", "/pricing"],
        "external_links": [], "images_alt_text": [], "schema_markup": None,
        "page_type": "service_page", "language": "en",
        "render_mode": "playwright",
    }

    crawler = CrawlerService(db_session)
    crawler._fetch_and_parse = AsyncMock(return_value=weak_page)
    crawler._fetch_with_playwright = AsyncMock(return_value=playwright_page)
    crawler._is_crawlable = MagicMock(return_value=True)
    crawler.max_pages = 1

    await crawler.crawl_site(project, max_pages=1, use_js=True)
    crawler._fetch_with_playwright.assert_called_once()

    q = await db_session.execute(select(Page).where(Page.project_id == project.id))
    pages = q.scalars().all()
    assert len(pages) > 0
    assert pages[0].render_mode == "playwright"
    assert pages[0].word_count == 500


@pytest.mark.asyncio
async def test_no_playwright_when_content_rich(db_session):
    """When httpx returns rich content (> 50 words), Playwright should NOT be called."""
    from app.services.crawler import CrawlerService

    project = Project(domain="static-rich.local", target_country="DE", target_language="de")
    db_session.add(project)
    await db_session.flush()

    rich_page = {
        "url": "https://static-rich.local/", "status_code": 200,
        "title": "Rich Static Page", "h1": "Main Heading",
        "h2": ["Section 1", "Section 2"], "h3": [],
        "content": "Rich content with many words. " * 100, "word_count": 400,
        "canonical_url": None, "indexable": True,
        "internal_links": ["/page1", "/page2"],
        "external_links": [], "images_alt_text": [], "schema_markup": None,
        "page_type": "landing_page", "language": "en", "render_mode": "http",
    }

    crawler = CrawlerService(db_session)
    crawler._fetch_and_parse = AsyncMock(return_value=rich_page)
    crawler._fetch_with_playwright = AsyncMock(return_value=None)
    crawler._is_crawlable = MagicMock(return_value=True)
    crawler.max_pages = 1

    await crawler.crawl_site(project, max_pages=1, use_js=True)
    crawler._fetch_with_playwright.assert_not_called()

    q = await db_session.execute(select(Page).where(Page.project_id == project.id))
    pages = q.scalars().all()
    assert len(pages) > 0
    assert pages[0].render_mode == "http"
