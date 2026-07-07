"""
Website crawler service using httpx + Trafilatura + selectolax + BeautifulSoup.
Extracts pages, metadata, content, headings, links, and schema.
Uses selectolax for fast HTML parsing, BeautifulSoup as fallback.
"""

import asyncio
import hashlib
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser as SelectolaxParser
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from trafilatura import extract as trafilatura_extract
from trafilatura.metadata import extract_metadata as trafilatura_metadata

from app.core.config import settings
from app.models import Project, Page


class CrawlerService:
    """Service for crawling own websites and extracting SEO-relevant data."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_agent = settings.crawler_user_agent
        self.rate_limit = settings.crawler_rate_limit
        self.max_pages = settings.crawler_max_pages
        self.visited: set = set()
        self.to_visit: list = []
        self._playwright = None

    async def crawl_site(
        self,
        project: Project,
        max_pages: int = 100,
        use_js: bool = False,
        start_path: str = "/",
    ) -> dict:
        """Crawl a project's website starting from the domain root."""
        self.max_pages = min(max_pages, settings.crawler_max_pages)
        base_url = f"https://{project.domain}" if not project.domain.startswith("http") else project.domain
        start_url = urljoin(base_url, start_path)

        self.to_visit = [(start_url, 0)]
        self.visited = set()
        pages_found = 0
        pages_crawled = 0
        errors = 0

        async with httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            while self.to_visit and pages_crawled < self.max_pages:
                url, depth = self.to_visit.pop(0)

                if url in self.visited:
                    continue
                self.visited.add(url)

                try:
                    render_mode = "http"
                    page_data = await self._fetch_and_parse(client, url, project.domain)

                    # Fallback to Playwright for JS-heavy pages:
                    # - httpx returned None (connection error)
                    # - Content is empty or very thin (< 50 words)
                    if use_js:
                        is_weak = (
                            page_data is None
                            or (page_data.get("word_count", 0) < 50)
                            or (not page_data.get("content"))
                        )
                        if is_weak:
                            page_data = await self._fetch_with_playwright(url, project.domain)
                            if page_data:
                                render_mode = "playwright"

                    if page_data:
                        page_data["render_mode"] = render_mode
                        await self._save_page(project.id, url, page_data, depth)
                        pages_crawled += 1

                        # Extract internal links to crawl
                        if depth < 4:
                            for link in page_data.get("internal_links", []):
                                full_url = urljoin(url, link)
                                full_url, _ = urldefrag(full_url)
                                if full_url not in self.visited and self._is_valid_url(full_url, project.domain):
                                    self.to_visit.append((full_url, depth + 1))

                    pages_found += 1

                except Exception:
                    errors += 1
                    continue

                # Rate limiting
                await asyncio.sleep(1.0 / self.rate_limit)

        return {
            "pages_crawled": pages_crawled,
            "pages_total_found": pages_found,
            "errors": errors,
        }

    async def _fetch_and_parse(
        self,
        client: httpx.AsyncClient,
        url: str,
        domain: str,
    ) -> Optional[dict]:
        """Fetch a URL and extract all SEO-relevant metadata."""
        try:
            # Check robots.txt first (simplified)
            if not self._is_crawlable(url, domain):
                return None

            response = await client.get(url)
            if response.status_code != 200:
                return {
                    "url": url,
                    "status_code": response.status_code,
                    "title": None,
                    "meta_description": None,
                    "h1": None,
                    "h2": [],
                    "h3": [],
                    "content": None,
                    "word_count": 0,
                    "canonical_url": None,
                    "indexable": response.status_code == 200,
                    "internal_links": [],
                    "external_links": [],
                    "images_alt_text": [],
                    "schema_markup": None,
                    "page_type": None,
                    "language": None,
                }

            html = response.text

            # Try selectolax first for speed, fall back to BeautifulSoup
            try:
                tree = SelectolaxParser(html)
                use_selectolax = True
            except Exception:
                tree = None
                use_selectolax = False

            soup = BeautifulSoup(html, "html.parser")

            # Extract with Trafilatura for clean content
            content = trafilatura_extract(html, include_images=False, include_tables=True)
            metadata = trafilatura_metadata(html) or {}

            # Extract headings (selectolax is ~2x faster)
            if use_selectolax and tree:
                h1_tags = [node.text(strip=True) for node in tree.css("h1")]
                h2_tags = [node.text(strip=True) for node in tree.css("h2")]
                h3_tags = [node.text(strip=True) for node in tree.css("h3")]
            else:
                h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
                h2_tags = [h.get_text(strip=True) for h in soup.find_all("h2")]
                h3_tags = [h.get_text(strip=True) for h in soup.find_all("h3")]

            # Extract links
            internal_links = []
            external_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("#") or href.startswith("javascript:"):
                    continue
                if domain in href or href.startswith("/"):
                    internal_links.append(href)
                elif href.startswith("http"):
                    external_links.append(href)

            # Extract images with alt text
            images_alt = []
            for img in soup.find_all("img"):
                alt = img.get("alt", "")
                src = img.get("src", "")
                if src:
                    images_alt.append({"src": src, "alt": alt})

            # Extract schema markup
            schema_markup = []
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    import json
                    schema_markup.append(json.loads(script.string))
                except Exception:
                    pass

            # Detect page type
            page_type = self._detect_page_type(url, soup)

            # Detect language
            html_tag = soup.find("html")
            language = html_tag.get("lang") if html_tag else None

            # Get meta tags
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else None

            meta_desc = soup.find("meta", attrs={"name": "description"})
            meta_description = meta_desc.get("content", "").strip() if meta_desc else None

            canonical = soup.find("link", rel="canonical")
            canonical_url = canonical.get("href") if canonical else None

            robots = soup.find("meta", attrs={"name": "robots"})
            indexable = True
            if robots:
                content = robots.get("content", "")
                if "noindex" in content:
                    indexable = False

            word_count = len(content.split()) if content else 0

            return {
                "url": url,
                "status_code": response.status_code,
                "title": title,
                "meta_description": meta_description,
                "h1": h1_tags[0] if h1_tags else None,
                "h2": h2_tags,
                "h3": h3_tags,
                "content": content,
                "word_count": word_count,
                "canonical_url": canonical_url,
                "indexable": indexable,
                "internal_links": list(set(internal_links)),
                "external_links": list(set(external_links)),
                "images_alt_text": images_alt,
                "schema_markup": schema_markup if schema_markup else None,
                "page_type": page_type,
                "language": language,
            }

        except httpx.HTTPError:
            return None
        except Exception:
            return None

    async def _save_page(
        self,
        project_id: str,
        url: str,
        page_data: dict,
        depth: int,
    ) -> None:
        """Save or update a crawled page in the database."""
        # Check if page already exists
        result = await self.db.execute(
            select(Page).where(
                Page.project_id == project_id,
                Page.url == url,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            existing.title = page_data.get("title")
            existing.meta_description = page_data.get("meta_description")
            existing.h1 = page_data.get("h1")
            existing.h2 = page_data.get("h2", [])
            existing.h3 = page_data.get("h3", [])
            existing.content = page_data.get("content")
            existing.content_cleaned = page_data.get("content")
            existing.word_count = page_data.get("word_count", 0)
            existing.status_code = page_data.get("status_code")
            existing.canonical_url = page_data.get("canonical_url")
            existing.indexable = page_data.get("indexable", True)
            existing.internal_links = page_data.get("internal_links", [])
            existing.external_links = page_data.get("external_links", [])
            existing.images_alt_text = page_data.get("images_alt_text", [])
            existing.schema_markup = page_data.get("schema_markup")
            existing.page_type = page_data.get("page_type")
            existing.language = page_data.get("language")
            existing.render_mode = page_data.get("render_mode", "http")
            existing.crawl_depth = depth
            existing.last_crawled_at = datetime.utcnow()
        else:
            # Create new page entry
            page = Page(
                project_id=project_id,
                url=url,
                title=page_data.get("title"),
                meta_description=page_data.get("meta_description"),
                h1=page_data.get("h1"),
                h2=page_data.get("h2", []),
                h3=page_data.get("h3", []),
                content=page_data.get("content"),
                content_cleaned=page_data.get("content"),
                word_count=page_data.get("word_count", 0),
                status_code=page_data.get("status_code"),
                canonical_url=page_data.get("canonical_url"),
                indexable=page_data.get("indexable", True),
                internal_links=page_data.get("internal_links", []),
                external_links=page_data.get("external_links", []),
                images_alt_text=page_data.get("images_alt_text", []),
                schema_markup=page_data.get("schema_markup"),
                page_type=page_data.get("page_type"),
                language=page_data.get("language"),
                render_mode=page_data.get("render_mode", "http"),
                crawl_depth=depth,
                is_own_site=True,
                last_crawled_at=datetime.utcnow(),
            )
            self.db.add(page)

        await self.db.flush()

    def _detect_page_type(self, url: str, soup: BeautifulSoup) -> str:
        """Detect the type of page based on URL and content."""
        path = urlparse(url).path.lower()

        if path in ["/", "/home", "/index", ""]:
            return "home_page"
        if any(x in path for x in ["/blog/", "/blog", "/article/", "/news/"]):
            return "blog_post"
        if any(x in path for x in ["/contact", "/kontakt", "/contact-us"]):
            return "contact_page"
        if any(x in path for x in ["/about", "/uber", "/about-us"]):
            return "about_page"
        if any(x in path for x in ["/faq", "/help", "/support"]):
            return "faq_page"
        if any(x in path for x in ["/product", "/produkt", "/shop"]):
            return "product_page"
        if any(x in path for x in ["/category", "/kategorie"]):
            return "category_page"
        if any(x in path for x in ["/service", "/leistung"]):
            return "service_page"

        return "landing_page"

    def _is_valid_url(self, url: str, domain: str) -> bool:
        """Check if URL is valid and belongs to the target domain."""
        parsed = urlparse(url)
        if not parsed.scheme.startswith("http"):
            return False
        if domain not in parsed.netloc:
            return False
        # Skip non-HTML resources
        skip_extensions = [".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                           ".pdf", ".zip", ".doc", ".docx", ".ico", ".woff", ".woff2"]
        if any(url.lower().endswith(ext) for ext in skip_extensions):
            return False
        # Skip anchors and tracking
        if "#" in url or "?" in url:
            return False
        return True

    async def _fetch_with_playwright(self, url: str, domain: str) -> Optional[dict]:
        """
        Fetch a page using Playwright for JavaScript-rendered content.
        Used as fallback when httpx returns empty/unusable content.
        Requires: playwright install chromium
        """
        try:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()

            soup = BeautifulSoup(html, "html.parser")
            content = trafilatura_extract(html, include_images=False, include_tables=True)

            h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
            h2_tags = [h.get_text(strip=True) for h in soup.find_all("h2")]
            h3_tags = [h.get_text(strip=True) for h in soup.find_all("h3")]

            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else None

            meta_desc = soup.find("meta", attrs={"name": "description"})
            meta_description = meta_desc.get("content", "").strip() if meta_desc else None

            canonical = soup.find("link", rel="canonical")
            canonical_url = canonical.get("href") if canonical else None

            internal_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if domain in href or href.startswith("/"):
                    internal_links.append(href)

            word_count = len(content.split()) if content else 0

            await browser.close()
            await pw.stop()

            return {
                "url": url,
                "status_code": 200,
                "title": title,
                "meta_description": meta_description,
                "h1": h1_tags[0] if h1_tags else None,
                "h2": h2_tags,
                "h3": h3_tags,
                "content": content,
                "word_count": word_count,
                "canonical_url": canonical_url,
                "indexable": True,
                "internal_links": list(set(internal_links)),
                "external_links": [],
                "images_alt_text": [],
                "schema_markup": None,
                "page_type": self._detect_page_type(url, soup),
                "language": None,
            }

        except ImportError:
            return None
        except Exception:
            return None

    def _is_crawlable(self, url: str, domain: str) -> bool:
        """Simplified robots.txt and crawl policy check."""
        # Skip admin, login, cart pages
        skip_patterns = [
            "/wp-admin", "/wp-login", "/admin", "/login",
            "/cart", "/checkout", "/my-account", "/account",
            "/cdn-cgi", "/tracking", "/print",
        ]
        url_lower = url.lower()
        for pattern in skip_patterns:
            if pattern in url_lower:
                return False
        return True
