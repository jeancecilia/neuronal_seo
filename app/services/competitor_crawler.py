"""
Competitor crawler using sitemap-first approach.
Extracts competitor page structure from sitemaps, then crawls key pages
for content, entities, FAQs, trust signals, and topic mapping.
"""

import asyncio
from datetime import datetime
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser as SelectolaxParser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from trafilatura import extract as trafilatura_extract

from app.core.config import settings
from app.models import Project, CompetitorPage
from app.services.sitemap_extractor import SitemapExtractor
from app.services.page_classifier import PageClassifier
from app.services.entity_extractor import EntityExtractor


class CompetitorCrawler:
    """
    Crawls competitor websites using sitemap-first approach.
    1. Extract sitemap to discover all competitor pages
    2. Classify pages by type
    3. Prioritize: service pages, landing pages, blog, FAQ
    4. Crawl high-priority pages for content analysis
    5. Extract entities (services, tech, pricing, trust, FAQ)
    6. Build topic map for gap analysis
    """

    PRIORITY_TYPES = [
        "service_page", "landing_page", "blog_article",
        "faq_page", "comparison_page", "case_study",
    ]

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_agent = settings.crawler_user_agent
        self.rate_limit = settings.crawler_rate_limit
        self.classifier = PageClassifier()
        self.entity_extractor = EntityExtractor()
        self.sitemap_extractor = SitemapExtractor()

    async def crawl_competitors_sitemap_first(
        self,
        project: Project,
        max_pages_per_competitor: int = 30,
    ) -> dict:
        """
        Crawl competitors using sitemap-first discovery.
        Extracts sitemaps, classifies pages, and crawls high-priority ones.
        """
        competitors = project.competitors or []
        if not competitors:
            return {"crawled": 0, "error": "No competitors configured"}

        results = {}
        total_crawled = 0

        for competitor_domain in competitors:
            try:
                # Step 1: Extract sitemap
                sitemap_data = await self.sitemap_extractor.extract_from_domain(
                    competitor_domain
                )
                all_pages = sitemap_data.get("pages", [])

                # Step 2: Quick classify all pages by URL only
                classified = []
                for page in all_pages:
                    page_type, confidence = self.classifier._classify_by_url(
                        page["url"]
                    )
                    classified.append({
                        "url": page["url"],
                        "page_type": page_type or "generic_page",
                        "confidence": confidence,
                        "last_modified": page.get("last_modified"),
                        "priority": page.get("priority"),
                    })

                # Step 3: Prioritize pages to crawl
                priority_pages = sorted(
                    [p for p in classified if p["page_type"] in self.PRIORITY_TYPES],
                    key=lambda p: (
                        self.PRIORITY_TYPES.index(p["page_type"])
                        if p["page_type"] in self.PRIORITY_TYPES
                        else 999
                    ),
                )[:max_pages_per_competitor]

                # Step 4: Crawl priority pages
                crawled_pages = []
                async with httpx.AsyncClient(
                    headers={"User-Agent": self.user_agent},
                    follow_redirects=True,
                    timeout=30.0,
                ) as client:
                    for pp in priority_pages:
                        try:
                            page_data = await self._fetch_and_analyze_page(
                                client, pp["url"]
                            )
                            if page_data:
                                await self._save_competitor_page(
                                    project.id,
                                    url=pp["url"],
                                    domain=competitor_domain,
                                    page_data=page_data,
                                    page_type=pp["page_type"],
                                )
                                crawled_pages.append(page_data)
                                total_crawled += 1

                            await asyncio.sleep(1.0 / self.rate_limit)

                        except Exception:
                            continue

                results[competitor_domain] = {
                    "sitemap_pages_found": len(all_pages),
                    "priority_pages_selected": len(priority_pages),
                    "pages_crawled": len(crawled_pages),
                    "page_types_found": list(set(
                        p["page_type"] for p in classified
                        if p["page_type"] != "generic_page"
                    )),
                }

            except Exception as e:
                results[competitor_domain] = {"error": str(e)}

        # Step 5: Build competitor topic map
        topic_map = await self._build_topic_map(project.id)

        return {
            "competitors_processed": len(results),
            "total_pages_crawled": total_crawled,
            "results": results,
            "topic_map": topic_map,
        }

    async def crawl_competitors(
        self,
        project: Project,
        max_per_keyword: int = 5,
    ) -> dict:
        """
        Legacy method: crawl competitors from SERP results.
        Now delegates to sitemap-first approach.
        """
        return await self.crawl_competitors_sitemap_first(project)

    async def crawl_manual_urls(
        self,
        project: Project,
        urls: List[str],
    ) -> dict:
        """
        Crawl manually provided competitor URLs.
        Used for manual SERP seeding - user provides top 5-10 URLs per keyword.
        """
        crawled = 0
        errors = 0

        async with httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for url in urls:
                try:
                    page_data = await self._fetch_and_analyze_page(client, url)
                    if page_data:
                        from urllib.parse import urlparse
                        domain = urlparse(url).netloc.replace("www.", "")
                        await self._save_competitor_page(
                            project.id,
                            url=url,
                            domain=domain,
                            page_data=page_data,
                            page_type=page_data.get("classification", {}).get("page_type"),
                        )
                        crawled += 1

                    await asyncio.sleep(1.0 / self.rate_limit)

                except Exception:
                    errors += 1
                    continue

        return {"crawled": crawled, "errors": errors}

    async def _fetch_and_analyze_page(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> Optional[dict]:
        """Fetch a page and run full analysis: classification + entity extraction."""
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return None

            html = response.text

            # Trafilatura for clean content
            content = trafilatura_extract(html, include_images=False, include_tables=True)

            # BeautifulSoup for structure
            soup = BeautifulSoup(html, "html.parser")

            # Try selectolax for faster heading extraction
            headings = {"h1": [], "h2": [], "h3": []}
            try:
                tree = SelectolaxParser(html)
                headings["h1"] = [node.text(strip=True) for node in tree.css("h1")]
                headings["h2"] = [node.text(strip=True) for node in tree.css("h2")]
                headings["h3"] = [node.text(strip=True) for node in tree.css("h3")]
            except Exception:
                headings["h1"] = [h.get_text(strip=True) for h in soup.find_all("h1")]
                headings["h2"] = [h.get_text(strip=True) for h in soup.find_all("h2")]
                headings["h3"] = [h.get_text(strip=True) for h in soup.find_all("h3")]

            all_headings = headings["h1"] + headings["h2"] + headings["h3"]

            # Title
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            meta_text = meta_desc.get("content", "").strip() if meta_desc else ""

            # Word count
            word_count = len(content.split()) if content else 0

            # Run page classification
            classification = self.classifier.classify(
                url=url,
                title=title,
                headings=all_headings,
                content=content or "",
                word_count=word_count,
            )

            # Run entity extraction
            entities = self.entity_extractor.extract(
                content=content or "",
                title=title,
                headings=all_headings,
                url=url,
            )

            # Trust/pricing/FAQ signals
            has_pricing = len(entities.get("pricing_terms", [])) > 0
            has_trust_signals = len(entities.get("trust_signals", [])) > 0
            has_local_refs = len(entities.get("local_references", [])) > 0
            has_cta = len(entities.get("cta_patterns", [])) > 0

            # Extract schema from JSON-LD
            schema_types = []
            try:
                import json
                for script in soup.find_all("script", type="application/ld+json"):
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get("@type"):
                        schema_types.append(data["@type"])
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get("@type"):
                                schema_types.append(item["@type"])
            except Exception:
                pass

            # Content sections from headings
            content_sections = []
            for h2 in headings["h2"]:
                content_sections.append({
                    "heading": h2,
                    "level": "h2",
                })

            return {
                "title": title,
                "meta_description": meta_text,
                "headings": headings,
                "content": content,
                "content_sections": content_sections,
                "faqs": entities.get("faqs", []),
                "schema_types": list(set(schema_types)),
                "has_pricing": has_pricing,
                "has_trust_signals": has_trust_signals,
                "has_case_studies": classification.get("page_type") == "case_study",
                "has_local_refs": has_local_refs,
                "has_cta": has_cta,
                "word_count": word_count,
                "entities": entities,
                "classification": classification,
            }

        except Exception:
            return None

    async def _save_competitor_page(
        self,
        project_id: str,
        url: str,
        domain: str,
        page_data: dict,
        page_type: Optional[str] = None,
    ) -> None:
        """Save or update a competitor page in the database."""
        existing = await self.db.execute(
            select(CompetitorPage).where(
                CompetitorPage.project_id == project_id,
                CompetitorPage.url == url,
            )
        )
        cp = existing.scalar_one_or_none()

        classification = page_data.get("classification", {})
        entities = page_data.get("entities", {})

        if cp:
            cp.title = page_data.get("title")
            cp.meta_description = page_data.get("meta_description")
            cp.headings = page_data.get("headings")
            cp.content = page_data.get("content")
            cp.content_sections = page_data.get("content_sections", [])
            cp.faqs = page_data.get("faqs", [])
            cp.schema_types = page_data.get("schema_types", [])
            cp.has_pricing = page_data.get("has_pricing", False)
            cp.has_trust_signals = page_data.get("has_trust_signals", False)
            cp.has_case_studies = page_data.get("has_case_studies", False)
            cp.has_local_refs = page_data.get("has_local_refs", False)
            cp.has_cta = page_data.get("has_cta", False)
            cp.word_count = page_data.get("word_count", 0)
            cp.entities = entities
            cp.fetched_at = datetime.utcnow()
        else:
            cp = CompetitorPage(
                project_id=project_id,
                url=url,
                domain=domain,
                title=page_data.get("title"),
                meta_description=page_data.get("meta_description"),
                headings=page_data.get("headings"),
                content=page_data.get("content"),
                content_sections=page_data.get("content_sections", []),
                faqs=page_data.get("faqs", []),
                schema_types=page_data.get("schema_types", []),
                has_pricing=page_data.get("has_pricing", False),
                has_trust_signals=page_data.get("has_trust_signals", False),
                has_case_studies=page_data.get("has_case_studies", False),
                has_local_refs=page_data.get("has_local_refs", False),
                has_cta=page_data.get("has_cta", False),
                word_count=page_data.get("word_count", 0),
                entities=entities,
                fetched_at=datetime.utcnow(),
            )
            self.db.add(cp)

        await self.db.flush()

    async def _build_topic_map(self, project_id: str) -> dict:
        """Build a topic map from all crawled competitor pages."""
        result = await self.db.execute(
            select(CompetitorPage).where(
                CompetitorPage.project_id == project_id,
            )
        )
        pages = result.scalars().all()

        page_dicts = [
            {"entities": p.entities or {}, "title": p.title or "", "url": p.url}
            for p in pages
        ]

        return self.entity_extractor.build_topic_map(page_dicts)
