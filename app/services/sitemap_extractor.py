"""
Sitemap extractor service.
Finds, downloads, and parses XML sitemaps from websites.
Extracts all URLs, their priorities, change frequencies, and last modified dates.
"""

import asyncio
import gzip
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


class SitemapExtractor:
    """
    Finds and extracts all URLs from website XML sitemaps and sitemap indexes.
    Works for both own sites and competitor sites.
    """

    SITEMAP_LOCATIONS = [
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/sitemap-index.xml",
        "/page-sitemap.xml",
        "/post-sitemap.xml",
        "/category-sitemap.xml",
        "/product-sitemap.xml",
        "/wp-sitemap.xml",  # WordPress
        "/sitemaps/sitemap.xml",
        "/sitemap/sitemap.xml",
        "/robots.txt",  # Often contains Sitemap: directive
    ]

    def __init__(self):
        self.user_agent = settings.crawler_user_agent
        self.rate_limit = settings.crawler_rate_limit

    async def extract_from_domain(self, domain: str) -> Dict:
        """
        Extract all sitemap URLs from a domain.
        Returns dict with sitemap_urls and page_urls.
        """
        base_url = f"https://{domain}" if not domain.startswith("http") else domain

        async with httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            # Step 1: Find sitemap URLs
            sitemap_urls = await self._find_sitemaps(client, base_url)

            # Step 2: Parse all sitemaps
            all_pages = []
            for sitemap_url in sitemap_urls:
                pages = await self._parse_sitemap(client, sitemap_url)
                all_pages.extend(pages)
                await asyncio.sleep(1.0 / self.rate_limit)

        # Deduplicate by URL
        seen = set()
        unique_pages = []
        for page in all_pages:
            if page["url"] not in seen:
                seen.add(page["url"])
                unique_pages.append(page)

        return {
            "domain": domain,
            "sitemap_urls": sitemap_urls,
            "total_pages": len(unique_pages),
            "pages": unique_pages,
        }

    async def _find_sitemaps(
        self, client: httpx.AsyncClient, base_url: str
    ) -> List[str]:
        """Find all sitemap URLs for a domain."""
        found_sitemaps = set()

        # Check known sitemap locations
        for path in self.SITEMAP_LOCATIONS:
            try:
                url = urljoin(base_url, path)
                response = await client.head(url)
                if response.status_code == 200 and "xml" in response.headers.get(
                    "content-type", ""
                ):
                    found_sitemaps.add(url)
            except Exception:
                continue

        # Also try to GET robots.txt for Sitemap: directives
        try:
            robots_url = urljoin(base_url, "/robots.txt")
            response = await client.get(robots_url)
            if response.status_code == 200:
                for line in response.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        if sitemap_url.startswith("http"):
                            found_sitemaps.add(sitemap_url)
                        else:
                            found_sitemaps.add(urljoin(base_url, sitemap_url))
        except Exception:
            pass

        return list(found_sitemaps)

    async def _parse_sitemap(
        self, client: httpx.AsyncClient, sitemap_url: str
    ) -> List[Dict]:
        """Parse a sitemap XML file and extract all URLs."""
        pages = []

        try:
            response = await client.get(sitemap_url)
            if response.status_code != 200:
                return pages

            content = response.content

            # Handle gzipped sitemaps
            if sitemap_url.endswith(".gz") or response.headers.get("content-type") == "application/gzip":
                try:
                    content = gzip.decompress(content)
                except Exception:
                    pass

            # Parse XML
            root = ET.fromstring(content)

            # Handle sitemap index (contains links to other sitemaps)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            sitemap_tags = root.findall(".//sm:sitemap/sm:loc", ns)
            if not sitemap_tags:
                sitemap_tags = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")

            if sitemap_tags:
                # This is a sitemap index - recursively parse sub-sitemaps
                for sm_tag in sitemap_tags[:20]:  # Limit sub-sitemaps
                    sub_url = sm_tag.text.strip() if sm_tag.text else ""
                    if sub_url:
                        sub_pages = await self._parse_sitemap(client, sub_url)
                        pages.extend(sub_pages)
                        await asyncio.sleep(0.5 / self.rate_limit)
                return pages

            # Parse regular URL entries
            url_tags = root.findall(".//sm:url", ns)
            if not url_tags:
                url_tags = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url")

            for url_elem in url_tags:
                loc_elem = url_elem.find("sm:loc", ns)
                if loc_elem is None:
                    loc_elem = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")

                lastmod_elem = url_elem.find("sm:lastmod", ns)
                if lastmod_elem is None:
                    lastmod_elem = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod")

                priority_elem = url_elem.find("sm:priority", ns)
                if priority_elem is None:
                    priority_elem = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}priority")

                changefreq_elem = url_elem.find("sm:changefreq", ns)
                if changefreq_elem is None:
                    changefreq_elem = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}changefreq")

                url = loc_elem.text.strip() if loc_elem is not None and loc_elem.text else ""
                if url:
                    pages.append({
                        "url": url,
                        "last_modified": lastmod_elem.text if lastmod_elem is not None and lastmod_elem.text else None,
                        "priority": float(priority_elem.text) if priority_elem is not None and priority_elem.text else None,
                        "change_frequency": changefreq_elem.text if changefreq_elem is not None and changefreq_elem.text else None,
                        "source_sitemap": sitemap_url,
                    })

        except ET.ParseError:
            pass
        except Exception:
            pass

        return pages


    async def extract_competitor_sitemaps(
        self, competitor_domains: List[str]
    ) -> Dict[str, Dict]:
        """Extract sitemaps from multiple competitor domains."""
        results = {}
        for domain in competitor_domains:
            try:
                results[domain] = await self.extract_from_domain(domain)
            except Exception as e:
                results[domain] = {"error": str(e), "pages": []}
            await asyncio.sleep(1.0)
        return results
