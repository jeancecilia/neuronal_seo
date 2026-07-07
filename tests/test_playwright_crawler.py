"""
Test that Playwright JS rendering fallback works correctly.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Project, Page
from sqlalchemy import select


@pytest.mark.asyncio
async def test_playwright_fallback_on_weak_content(db_session):
    """
    When httpx returns content with < 50 words and use_js=True,
    the crawler should fall back to Playwright.
    """
    from app.services.crawler import CrawlerService

    project = Project(
        domain="js-heavy.local",
        target_country="DE",
        target_language="de",
    )
    db_session.add(project)
    await db_session.flush()

    # Mock httpx to return weak content (< 50 words)
    weak_page = {
        "url": "https://js-heavy.local/",
        "status_code": 200,
        "title": "JS App",
        "meta_description": None,
        "h1": "Loading...",
        "h2": [],
        "h3": [],
        "content": "Loading... Please wait.",
        "word_count": 3,  # Very weak content
        "canonical_url": None,
        "indexable": True,
        "internal_links": [],
        "external_links": [],
        "images_alt_text": [],
        "schema_markup": None,
        "page_type": "landing_page",
        "language": "en",
    }

    # Mock Playwright to return rich content
    playwright_page = {
        "url": "https://js-heavy.local/",
        "status_code": 200,
        "title": "Full Rendered Page",
        "meta_description": "Rendered description",
        "h1": "Welcome to Our Service",
        "h2": ["Services", "Pricing", "Contact"],
        "h3": [],
        "content": "This is the fully rendered content after JavaScript execution. " * 50,
        "word_count": 500,
        "canonical_url": None,
        "indexable": True,
        "internal_links": ["/services", "/pricing"],
        "external_links": [],
        "images_alt_text": [],
        "schema_markup": None,
        "page_type": "service_page",
        "language": "en",
        "render_mode": "playwright",
    }

    crawler = CrawlerService(db_session)
    crawler._fetch_and_parse = AsyncMock(return_value=weak_page)
    crawler._fetch_with_playwright = AsyncMock(return_value=playwright_page)
    crawler._is_crawlable = MagicMock(return_value=True)
    crawler.max_pages = 1

    # Run with use_js=True
    result = await crawler.crawl_site(project, max_pages=1, use_js=True)

    # Verify Playwright was called (because content was weak)
    crawler._fetch_with_playwright.assert_called_once()

    # Verify the page was saved with playwright render_mode
    q = await db_session.execute(
        select(Page).where(Page.project_id == project.id)
    )
    pages = q.scalars().all()
    assert len(pages) > 0, "Page should be saved after Playwright fallback"
    assert pages[0].render_mode == "playwright"
    assert pages[0].word_count == 500  # Should use the Playwright-rich content


@pytest.mark.asyncio
async def test_no_playwright_when_content_rich(db_session):
    """
    When httpx returns rich content (> 50 words), Playwright should NOT be called.
    """
    from app.services.crawler import CrawlerService

    project = Project(
        domain="static-rich.local",
        target_country="DE",
        target_language="de",
    )
    db_session.add(project)
    await db_session.flush()

    rich_page = {
        "url": "https://static-rich.local/",
        "status_code": 200,
        "title": "Rich Static Page",
        "meta_description": "A good description",
        "h1": "Main Heading",
        "h2": ["Section 1", "Section 2"],
        "h3": [],
        "content": "Rich content with many words. " * 100,
        "word_count": 400,
        "canonical_url": None,
        "indexable": True,
        "internal_links": ["/page1", "/page2"],
        "external_links": [],
        "images_alt_text": [],
        "schema_markup": None,
        "page_type": "landing_page",
        "language": "en",
        "render_mode": "http",
    }

    crawler = CrawlerService(db_session)
    crawler._fetch_and_parse = AsyncMock(return_value=rich_page)
    crawler._fetch_with_playwright = AsyncMock(return_value=None)
    crawler._is_crawlable = MagicMock(return_value=True)
    crawler.max_pages = 1

    await crawler.crawl_site(project, max_pages=1, use_js=True)

    # Playwright should NOT be called because httpx returned good content
    crawler._fetch_with_playwright.assert_not_called()

    q = await db_session.execute(
        select(Page).where(Page.project_id == project.id)
    )
    pages = q.scalars().all()
    assert len(pages) > 0
    assert pages[0].render_mode == "http"
