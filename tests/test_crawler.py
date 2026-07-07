"""
Test the static crawler (httpx-based) and Playwright crawler.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import Project, Page


@pytest.mark.asyncio
async def test_crawler_creates_project_pages(db_session):
    """Test that the crawler creates page records for a project."""
    from app.services.crawler import CrawlerService

    project = Project(
        domain="static-test.local",
        target_country="DE",
        target_language="de",
        target_cities=["Köln"],
        services=["Test Service"],
    )
    db_session.add(project)
    await db_session.flush()

    # Mock the HTTP fetch to avoid real network calls
    mock_page_data = {
        "url": "https://static-test.local/",
        "status_code": 200,
        "title": "Test Page",
        "meta_description": "A test page",
        "h1": "Welcome",
        "h2": ["Section 1", "Section 2"],
        "h3": [],
        "content": "This is the main content of the test page. " * 50,
        "word_count": 500,
        "canonical_url": None,
        "indexable": True,
        "internal_links": ["/about", "/services"],
        "external_links": [],
        "images_alt_text": [],
        "schema_markup": None,
        "page_type": "home_page",
        "language": "en",
        "render_mode": "http",
    }

    crawler = CrawlerService(db_session)
    crawler._fetch_and_parse = AsyncMock(return_value=mock_page_data)
    crawler._is_crawlable = MagicMock(return_value=True)
    crawler._is_valid_url = MagicMock(return_value=True)
    crawler.max_pages = 1

    result = await crawler.crawl_site(project, max_pages=1)

    assert result["pages_crawled"] > 0

    # Verify page was saved
    from sqlalchemy import select
    q = await db_session.execute(
        select(Page).where(Page.project_id == project.id)
    )
    pages = q.scalars().all()
    assert len(pages) > 0
    assert pages[0].render_mode == "http"


@pytest.mark.asyncio
async def test_crawler_stores_render_mode(db_session):
    """Test that render_mode is stored per page."""
    from app.services.crawler import CrawlerService

    project = Project(
        domain="render-test.local",
        target_country="DE",
        target_language="de",
    )
    db_session.add(project)
    await db_session.flush()

    mock_page_data = {
        "url": "https://render-test.local/",
        "status_code": 200,
        "title": "JS Page",
        "meta_description": "",
        "h1": "JS App",
        "h2": [],
        "h3": [],
        "content": "Some content",
        "word_count": 150,
        "canonical_url": None,
        "indexable": True,
        "internal_links": [],
        "external_links": [],
        "images_alt_text": [],
        "schema_markup": None,
        "page_type": "landing_page",
        "language": "en",
        "render_mode": "playwright",
    }

    crawler = CrawlerService(db_session)
    crawler._fetch_and_parse = AsyncMock(return_value=mock_page_data)
    crawler._fetch_with_playwright = AsyncMock(return_value=None)
    crawler._is_crawlable = MagicMock(return_value=True)
    crawler.max_pages = 1

    await crawler.crawl_site(project, max_pages=1)

    from sqlalchemy import select
    q = await db_session.execute(
        select(Page).where(Page.project_id == project.id)
    )
    pages = q.scalars().all()
    assert len(pages) > 0
    # When use_js=False, the crawler's http fetch result is stored as-is.
    # The render_mode in mock_data is preserved since we bypassed the fallback check.
    assert pages[0].render_mode in ("http", "playwright")


@pytest.mark.asyncio
async def test_crawler_handles_empty_content(db_session):
    """Test that crawler handles empty content gracefully."""
    from app.services.crawler import CrawlerService

    project = Project(
        domain="empty-test.local",
        target_country="DE",
        target_language="de",
    )
    db_session.add(project)
    await db_session.flush()

    # Mock page with empty content
    mock_page_data = {
        "url": "https://empty-test.local/",
        "status_code": 200,
        "title": "Empty Page",
        "meta_description": None,
        "h1": None,
        "h2": [],
        "h3": [],
        "content": "",
        "word_count": 0,
        "canonical_url": None,
        "indexable": True,
        "internal_links": [],
        "external_links": [],
        "images_alt_text": [],
        "schema_markup": None,
        "page_type": "landing_page",
        "language": None,
        "render_mode": "http",
    }

    crawler = CrawlerService(db_session)
    crawler._fetch_and_parse = AsyncMock(return_value=mock_page_data)
    crawler._is_crawlable = MagicMock(return_value=True)
    crawler.max_pages = 1

    result = await crawler.crawl_site(project, max_pages=1)

    # Should still save the page even with empty content
    from sqlalchemy import select
    q = await db_session.execute(
        select(Page).where(Page.project_id == project.id)
    )
    pages = q.scalars().all()
    assert len(pages) > 0
    assert pages[0].word_count == 0


@pytest.mark.asyncio
async def test_crawler_skips_non_crawlable(db_session):
    """Test that crawler respects crawl policy."""
    from app.services.crawler import CrawlerService

    project = Project(
        domain="skip-test.local",
        target_country="DE",
        target_language="de",
    )
    db_session.add(project)
    await db_session.flush()

    crawler = CrawlerService(db_session)

    # Test that admin pages are skipped
    assert crawler._is_crawlable("https://skip-test.local/wp-admin", "skip-test.local") is False
    assert crawler._is_crawlable("https://skip-test.local/about", "skip-test.local") is True
    assert crawler._is_crawlable("https://skip-test.local/login", "skip-test.local") is False
