"""
Keyword seed engine that generates keyword ideas from project context,
services, cities, competitors, and SERP data.
"""

from typing import List, Set
from itertools import product

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Keyword


class KeywordSeedEngine:
    """Generates seed keywords from project configuration without external data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_seeds(self, project: Project) -> List[str]:
        """Generate all seed keyword combinations for a project."""
        keywords: Set[str] = set()
        services = project.services or []
        cities = project.target_cities or []
        competitors = project.competitors or []
        brand_terms = project.brand_terms or []

        # 1. Service keywords alone
        for service in services:
            keywords.add(service.lower().strip())

        # 2. City + service combinations
        for city in cities:
            for service in services:
                keywords.add(f"{service} {city}".lower().strip())
                keywords.add(f"{service} in {city}".lower().strip())
                # German variants
                if project.target_language == "de":
                    keywords.add(f"{service} im raum {city}".lower().strip())

        # 3. Brand terms
        for term in brand_terms:
            keywords.add(term.lower().strip())

        # 4. Competitor-derived seeds (simplified - full version would crawl competitors)
        for competitor in competitors:
            keywords.add(f"alternative {competitor}".lower().strip())

        # 5. Common intent modifiers
        intent_modifiers = {
            "informational": ["was ist", "wie funktioniert", "anleitung", "guide", "erklärung"],
            "commercial": ["kosten", "preise", "erfahrungen", "bewertung", "vergleich", "test"],
            "transactional": ["kaufen", "beauftragen", "anbieter", "firma", "agentur", "experte"],
        }

        # Add intent-modified keywords for services
        for service in services:
            for intent_type, mods in intent_modifiers.items():
                for mod in mods[:3]:  # limit to top 3 per intent
                    keywords.add(f"{mod} {service}".lower().strip())

        # 6. Problem-solution combos
        problem_keywords = ["problem", "fehler", "reparieren", "optimieren", "erstellen", "entwickeln"]
        for problem in problem_keywords:
            for service in services[:3]:
                keywords.add(f"{service} {problem}".lower().strip())

        # 7. Common SEO question patterns
        question_patterns = ["was kostet", "wie lange dauert", "welche", "was ist der beste"]
        for q in question_patterns:
            for service in services[:3]:
                keywords.add(f"{q} {service}".lower().strip())

        # Remove empty, duplicates, and forbidden terms
        forbidden = set(t.lower() for t in (project.forbidden_terms or []))
        keywords = {
            kw.strip()
            for kw in keywords
            if kw.strip() and len(kw.strip()) > 3 and kw.strip() not in forbidden
        }

        # Save to database in batches
        saved_count = 0
        for kw_text in keywords:
            # Check for existing
            existing = await self.db.execute(
                select(Keyword).where(
                    Keyword.project_id == project.id,
                    Keyword.keyword == kw_text,
                )
            )
            if existing.scalar_one_or_none():
                continue

            kw = Keyword(
                project_id=project.id,
                keyword=kw_text,
                language=project.target_language,
                country=project.target_country,
                source="seed_generator",
            )
            self.db.add(kw)
            saved_count += 1

        await self.db.flush()
        return list(keywords)
