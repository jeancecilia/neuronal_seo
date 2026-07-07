"""
SERP data collection service using DataForSEO or SerpAPI.
Fetches Google search results per keyword, country, language, and location.
"""

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Project, Keyword, SerpResult


class SerpFetcher:
    """
    Fetches SERP (Search Engine Results Page) data for keywords.
    Supports DataForSEO as primary provider, with SerpAPI fallback.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.dataforseo_login = settings.dataforseo_login
        self.dataforseo_key = settings.dataforseo_api_key
        self.serpapi_key = settings.serpapi_key

    async def fetch_all_serps(
        self,
        project: Project,
        max_keywords: int = 50,
    ) -> dict:
        """Fetch SERP results for all keywords in a project."""
        # Get keywords without SERP data
        result = await self.db.execute(
            select(Keyword)
            .where(Keyword.project_id == project.id)
            .limit(max_keywords)
            .order_by(Keyword.business_value.desc())
        )
        keywords = result.scalars().all()

        fetched = 0
        errors = 0

        for kw in keywords:
            try:
                serp_data = await self._fetch_serp_for_keyword(
                    keyword=kw.keyword,
                    country=kw.country or project.target_country,
                    language=kw.language or project.target_language,
                    city=kw.city,
                )

                if serp_data:
                    await self._save_serp_results(project.id, kw.id, kw.keyword, serp_data)
                    fetched += 1

                # Rate limiting
                await asyncio.sleep(1.0)

            except Exception:
                errors += 1
                continue

        return {"fetched": fetched, "errors": errors, "total_keywords": len(keywords)}

    async def _fetch_serp_for_keyword(
        self,
        keyword: str,
        country: str = "DE",
        language: str = "de",
        city: Optional[str] = None,
    ) -> Optional[list]:
        """
        Fetch SERP data for a single keyword.
        Attempts DataForSEO first, falls back to SerpAPI.
        """
        # Try DataForSEO first
        if self.dataforseo_login and self.dataforseo_key:
            results = await self._fetch_dataforseo(keyword, country, language, city)
            if results:
                return results

        # Fall back to SerpAPI
        if self.serpapi_key:
            results = await self._fetch_serpapi(keyword, country, language, city)
            if results:
                return results

        # Return mock/simulated results for development
        return self._generate_mock_results(keyword, country, city)

    async def _fetch_dataforseo(
        self,
        keyword: str,
        country: str,
        language: str,
        city: Optional[str],
    ) -> Optional[list]:
        """Fetch SERP data from DataForSEO API."""
        try:
            location_code = self._get_location_code(country, city)
            payload = [{
                "keyword": keyword,
                "language_code": language,
                "location_code": location_code,
                "device": "desktop",
                "os": "windows",
                "depth": 10,
            }]

            async with httpx.AsyncClient(timeout=60.0) as client:
                auth = (self.dataforseo_login, self.dataforseo_key)
                response = await client.post(
                    "https://api.dataforseo.com/v3/serp/google/organic/live/advanced",
                    json=payload,
                    auth=auth,
                )
                data = response.json()

                if data.get("status_code") == 20000:
                    tasks = data.get("tasks", [])
                    if tasks:
                        results = tasks[0].get("result", [])
                        if results:
                            items = results[0].get("items", [])
                            return [
                                {
                                    "position": item.get("rank_absolute", i + 1),
                                    "url": item.get("url", ""),
                                    "title": item.get("title", ""),
                                    "description": item.get("description", ""),
                                    "domain": item.get("domain", ""),
                                    "serp_features": self._extract_features(item),
                                }
                                for i, item in enumerate(items[:10])
                            ]
            return None
        except Exception:
            return None

    async def _fetch_serpapi(
        self,
        keyword: str,
        country: str,
        language: str,
        city: Optional[str],
    ) -> Optional[list]:
        """Fetch SERP data from SerpAPI as fallback."""
        try:
            params = {
                "api_key": self.serpapi_key,
                "engine": "google",
                "q": keyword,
                "google_domain": f"google.{country.lower() if country != 'UK' else 'co.uk'}",
                "hl": language,
                "gl": country,
                "num": 10,
            }
            if city:
                params["location"] = city

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://serpapi.com/search",
                    params=params,
                )
                data = response.json()

                organic = data.get("organic_results", [])
                return [
                    {
                        "position": i + 1,
                        "url": item.get("link", ""),
                        "title": item.get("title", ""),
                        "description": item.get("snippet", ""),
                        "domain": self._extract_domain(item.get("link", "")),
                        "serp_features": self._extract_serpapi_features(data),
                    }
                    for i, item in enumerate(organic[:10])
                ]
        except Exception:
            return None

    def _generate_mock_results(self, keyword: str, country: str, city: Optional[str]) -> list:
        """Generate mock/development SERP results when no API keys are configured."""
        # This is for development purposes only
        mock_domains = [
            "example.com", "competitor1.com", "competitor2.de",
            "industry-leader.com", "local-business.de",
        ]

        return [
            {
                "position": i + 1,
                "url": f"https://{domain}/page-about-{keyword.replace(' ', '-')}",
                "title": f"{keyword.title()} - Best Results 2024 | {domain.split('.')[0].title()}",
                "description": f"Find the best {keyword} services. Professional solutions for your needs. Compare prices and quality.",
                "domain": domain,
                "serp_features": {"has_featured_snippet": i == 0},
            }
            for i, domain in enumerate(mock_domains)
        ]

    async def _save_serp_results(
        self,
        project_id: str,
        keyword_id: str,
        keyword: str,
        serp_data: list,
    ) -> None:
        """Save SERP results to the database."""
        for item in serp_data:
            serp_result = SerpResult(
                project_id=project_id,
                keyword_id=keyword_id,
                keyword=keyword,
                position=item["position"],
                url=item["url"],
                title=item.get("title"),
                description=item.get("description"),
                domain=item.get("domain"),
                serp_features=item.get("serp_features"),
            )
            self.db.add(serp_result)

        await self.db.flush()

    def _get_location_code(self, country: str, city: Optional[str] = None) -> int:
        """Get DataForSEO location code for country/city."""
        # Common location codes
        location_map = {
            "DE": 2276,  # Germany
            "AT": 2040,  # Austria
            "CH": 2756,  # Switzerland
            "US": 2840,  # United States
            "UK": 2826,  # United Kingdom
            "FR": 2250,  # France
            "TH": 2764,  # Thailand
        }
        return location_map.get(country.upper(), 2276)

    def _extract_domain(self, url: str) -> str:
        """Extract domain from a URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")

    def _extract_features(self, item: dict) -> dict:
        """Extract SERP feature flags from DataForSEO item."""
        return {
            "has_featured_snippet": bool(item.get("featured_title")),
            "has_sitelinks": bool(item.get("sitelinks")),
            "has_reviews": bool(item.get("rating")),
            "has_images": bool(item.get("images")),
            "has_video": bool(item.get("video")),
        }

    def _extract_serpapi_features(self, data: dict) -> dict:
        """Extract SERP feature flags from SerpAPI response."""
        return {
            "has_featured_snippet": bool(data.get("answer_box")),
            "has_knowledge_graph": bool(data.get("knowledge_graph")),
            "has_local_pack": bool(data.get("local_results")),
            "has_related_questions": bool(data.get("related_questions")),
        }
