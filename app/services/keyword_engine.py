"""Keyword seed engine with quality filtering.

Generates clean, business-relevant seed keywords from project configuration.
Filters out low-quality, too-generic, and exploration-style keywords.
"""

import re
import logging
from typing import List, Set
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Keyword

logger = logging.getLogger(__name__)

_QUALITY_BLACKLIST = [
    r"\bim raum\b",
    r"\braum\s+\w+",
    r"^beauftragen\b",
    r"^anleitung\b",
    r"^erklarung\b",
    r"^erfahrungen\b",
    r"^wie funktioniert\b",
    r"^welche\b",
    r"^was ist\b",
    r"^was kostet\b",
    r"^wo findet\b",
    r"^wer ist\b",
    r"^kann man\b",
    r"^muss man\b",
    r"^braucht man\b",
    r"^gibt es\b",
    r"\bfinden sie\b",
    r"\bsuchen sie\b",
    r"^hilfe bei\b",
    r"\bin der nahe\b",
    r"\bin meiner nahe\b",
]

_MAX_KEYWORD_WORDS = 5
_MIN_KEYWORD_LENGTH = 4


class KeywordSeedEngine:
    """Generates clean, business-relevant seed keywords from project config."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_seeds(self, project: Project) -> List[str]:
        """Generate seed keywords from project services, cities, and modifiers."""
        raw_keywords: Set[str] = set()
        services = project.services or []
        cities = project.target_cities or []

        for service in services:
            raw_keywords.add(service.lower().strip())

        for city in cities[:3]:
            for service in services:
                raw_keywords.add(f"{service} {city}".lower().strip())

        buying_modifiers = ["kosten", "preise", "anwalt", "beratung"]
        for service in services[:5]:
            for mod in buying_modifiers[:2]:
                if mod not in service.lower():
                    raw_keywords.add(f"{mod} {service}".lower().strip())

        keywords = self._filter_quality(raw_keywords)

        forbidden = set(t.lower().strip() for t in (project.forbidden_terms or []))
        keywords = {
            kw.strip()
            for kw in keywords
            if kw.strip()
            and len(kw.strip()) >= _MIN_KEYWORD_LENGTH
            and kw.strip() not in forbidden
        }

        await self._save_keywords(project.id, keywords)

        logger.info(
            "Generated %d seed keywords for project %s (from %d raw)",
            len(keywords),
            project.id,
            len(raw_keywords),
        )
        return list(keywords)

    def _filter_quality(self, keywords: Set[str]) -> Set[str]:
        """Remove low-quality, too-generic, and exploration-style keywords."""
        filtered: Set[str] = set()
        for kw in keywords:
            kw_clean = kw.strip().lower()
            if len(kw_clean) < _MIN_KEYWORD_LENGTH:
                continue
            if len(kw_clean.split()) > _MAX_KEYWORD_WORDS:
                continue
            if any(re.search(pattern, kw_clean, re.IGNORECASE) for pattern in _QUALITY_BLACKLIST):
                continue
            normalized = re.sub(r"\b(in|im|für|bei|mit|und|oder|der|die|das|ein|eine)\b", "", kw_clean)
            normalized = re.sub(r"\s+", " ", normalized).strip()
            if len(normalized) < _MIN_KEYWORD_LENGTH:
                continue
            filtered.add(kw_clean)
        return filtered

    async def _save_keywords(self, project_id: str, keywords: Set[str]) -> None:
        """Save generated seed keywords to the database, replacing existing seeds."""
        await self.db.execute(
            delete(Keyword).where(
                Keyword.project_id == project_id,
                Keyword.source.in_(["seed", "bootstrap"]),
            )
        )

        for kw in sorted(keywords):
            keyword = Keyword(
                project_id=project_id,
                keyword=kw,
                source="seed",
                search_volume=0,
                competition_index=0,
                cpc=0.0,
            )
            self.db.add(keyword)

        await self.db.flush()
