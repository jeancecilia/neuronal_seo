"""Keyword seed engine with quality filtering.

Generates clean, business-relevant seed keywords from project configuration.
Filters out low-quality, unnatural, city-stuffed, and exploration-style keywords.
"""

import re
import logging
from typing import List, Set
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Keyword

logger = logging.getLogger(__name__)

# Patterns that indicate low-quality / unnatural keywords
_QUALITY_BLACKLIST = [
    # Location-stuffed
    r"\bim raum\b", r"\braum\s+\w+", r"\bin der nahe\b", r"\bin meiner nahe\b",
    # Imperative / action-style (not search queries)
    r"^beauftragen\b", r"\bfinden sie\b", r"\bsuchen sie\b",
    # Tutorial / how-to (informational, not buying)
    r"^anleitung\b", r"^erklarung\b",
    # Review intent (not our content)
    r"^erfahrungen\b",
    # Exploration / vague
    r"^wie funktioniert\b", r"^welche\b", r"^was ist\b", r"^was kostet\b",
    r"^wo findet\b", r"^wer ist\b", r"^kann man\b", r"^muss man\b",
    r"^braucht man\b", r"^gibt es\b",
    # Generic help phrases
    r"^hilfe bei\b",
]

# Keyword patterns that produce unnatural German word order
_UNNATURAL_GERMAN = [
    # "entwicklung köln app" instead of "app entwicklung köln"
    (r"^entwicklung\s+(\w+)\s+(.+)", r"\2 entwicklung \1"),
    # "köln app agentur" instead of "app agentur köln"  
    (r"^(köln|bonn|düsseldorf)\s+(.+)", r"\2 \1"),
]

_MAX_KEYWORD_WORDS = 5
_MIN_KEYWORD_LENGTH = 4

# Cities we know about — don't create "city city" combinations
_KNOWN_CITIES = {
    "köln", "bonn", "düsseldorf", "leverkusen", "hürth", "frechen",
    "berlin", "hamburg", "münchen", "frankfurt", "stuttgart", "essen",
    "udon thani", "khon kaen", "nong khai", "sakon nakhon", "isaan",
    "bangkok", "chiang mai", "pattaya", "phuket",
}


class KeywordSeedEngine:
    """Generates clean, business-relevant seed keywords from project config."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_seeds(self, project: Project) -> List[str]:
        """Generate seed keywords from project services, cities, and modifiers."""
        raw_keywords: Set[str] = set()
        services = project.services or []
        cities = project.target_cities or []
        city_short = [c.lower().strip() for c in cities[:3]]

        # 1. Pure service names
        for service in services:
            s = service.lower().strip()
            if self._is_valid_service_keyword(s):
                raw_keywords.add(s)

        # 2. Service + City (one city per keyword, not stuffed)
        for city in city_short:
            for service in services:
                s = service.lower().strip()
                if city not in s:  # Avoid "köln seo köln"
                    raw_keywords.add(f"{s} {city}")

        # 3. Buying-intent modifier + Service (limited)
        buying_modifiers = ["kosten", "preise"]
        for service in services[:5]:
            s = service.lower().strip()
            for mod in buying_modifiers:
                if mod not in s:
                    raw_keywords.add(f"{mod} {s}")

        # 4. Quality filter
        keywords = self._filter_quality(raw_keywords)

        # 5. Remove forbidden terms
        forbidden = set(t.lower().strip() for t in (project.forbidden_terms or []))
        keywords = {
            kw.strip()
            for kw in keywords
            if kw.strip()
            and len(kw.strip()) >= _MIN_KEYWORD_LENGTH
            and kw.strip() not in forbidden
        }

        # 6. Fix unnatural German word order
        keywords = self._fix_word_order(keywords)

        # 7. Remove city-stuffed keywords (multiple cities in one keyword)
        keywords = self._remove_city_stuffed(keywords, city_short)

        await self._save_keywords(project.id, keywords)

        logger.info(
            "Generated %d seed keywords for project %s (from %d raw)",
            len(keywords), project.id, len(raw_keywords),
        )
        return list(keywords)

    def _is_valid_service_keyword(self, service: str) -> bool:
        """Check if a pure service name makes a valid keyword."""
        if len(service) < _MIN_KEYWORD_LENGTH:
            return False
        if any(re.search(p, service, re.IGNORECASE) for p in _QUALITY_BLACKLIST):
            return False
        if len(service.split()) > _MAX_KEYWORD_WORDS:
            return False
        return True

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
            # Normalize and check
            normalized = re.sub(r"\b(in|im|für|bei|mit|und|oder|der|die|das|ein|eine)\b", "", kw_clean)
            normalized = re.sub(r"\s+", " ", normalized).strip()
            if len(normalized) < _MIN_KEYWORD_LENGTH:
                continue
            filtered.add(kw_clean)
        return filtered

    def _fix_word_order(self, keywords: Set[str]) -> Set[str]:
        """Fix unnatural German word order in keywords."""
        fixed: Set[str] = set()
        for kw in keywords:
            modified = kw
            for pattern, replacement in _UNNATURAL_GERMAN:
                modified = re.sub(pattern, replacement, modified)
            fixed.add(modified.strip())
        return fixed

    def _remove_city_stuffed(self, keywords: Set[str], cities: List[str]) -> Set[str]:
        """Remove keywords that contain multiple city names (city stuffing)."""
        if len(cities) < 2:
            return keywords
        filtered: Set[str] = set()
        for kw in keywords:
            city_count = sum(1 for c in cities if c in kw.lower())
            if city_count <= 1:
                filtered.add(kw)
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
