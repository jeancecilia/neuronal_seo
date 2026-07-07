"""
Search intent classification service.
Classifies keywords and clusters into intent categories:
local_transactional, commercial, informational, comparison, problem_solution, brand, support, navigational.
"""

import asyncio
import re
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Project, Keyword, KeywordCluster, SerpResult


class IntentClassifier:
    """
    Classifies search intent using keyword patterns, SERP features, and LLM analysis.
    """

    # Keyword-based intent patterns
    INTENT_PATTERNS = {
        "local_transactional": [
            r"\b(?:in\s+)?(?:der\s+)?nähe\b", r"\bund\b", r"\bjetzt\b", r"\bheute\b",
            r"\bhier\b", r"\blokal\b", r"\bvor\s+ort\b", r"\bstandort\b",
            r"\bin\s+(?:köln|berlin|hamburg|münchen|frankfurt|düsseldorf|stuttgart|bonn)\b",
        ],
        "commercial": [
            r"\bkosten\b", r"\bpreis(?:e)?\b", r"\bgünstig\b", r"\bbillig\b",
            r"\berfahrungen\b", r"\btest\b", r"\bvergleich\b", r"\bbewertung\b",
            r"\bbeste\b", r"\btop\b", r"\branking\b", r"\bempfehlung\b",
        ],
        "informational": [
            r"\bwas\s+ist\b", r"\bwie\b", r"\bwarum\b", r"\bwelche\b",
            r"\banleitung\b", r"\bguide\b", r"\btutorial\b", r"\bwiki\b",
            r"\berklärung\b", r"\bdefinition\b", r"\bbedienung\b",
            r"\bbedeutung\b", r"\bunterschied\b",
        ],
        "comparison": [
            r"\bvs\.?\b", r"\boder\b", r"\bvergleich\b", r"\balternative\b",
            r"\bunterschied\b", r"\bgegen\b",
        ],
        "problem_solution": [
            r"\bproblem\b", r"\bfehler\b", r"\bfix\b", r"\blösung\b",
            r"\breparieren\b", r"\bkaputt\b", r"\bfunktioniert\s+nicht\b",
            r"\bhilfe\b", r"\bproblem\s+mit\b",
        ],
        "brand": [
            r"\bappagentur\b", r"\bagentur\s+name\b",  # Customize per project
        ],
        "navigational": [
            r"\blogin\b", r"\banmeldung\b", r"\bhomepage\b", r"\bwebseite\b",
            r"\bkontakt\b", r"\btelefon\b", r"\badresse\b", r"\böffnungszeiten\b",
        ],
    }

    SERP_INTENT_MAP = {
        "local_pack": "local_transactional",
        "featured_snippet": "informational",
        "knowledge_graph": "informational",
        "shopping_results": "commercial",
        "reviews": "commercial",
        "people_also_ask": "informational",
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.openai_key = settings.openai_api_key

    async def classify_all(self, project: Project) -> dict:
        """Classify intent for all keywords and clusters in a project."""
        # Classify individual keywords
        result = await self.db.execute(
            select(Keyword).where(Keyword.project_id == project.id)
        )
        keywords = result.scalars().all()

        classified = 0
        for kw in keywords:
            intent = await self._classify_keyword(kw, project)
            kw.intent = intent
            classified += 1

        await self.db.flush()

        # Classify clusters based on their keywords
        result = await self.db.execute(
            select(KeywordCluster).where(KeywordCluster.project_id == project.id)
        )
        clusters = result.scalars().all()

        for cluster in clusters:
            cluster_intent = await self._classify_cluster(cluster, project)
            cluster.intent = cluster_intent
            # Also update keywords in the cluster
            if cluster.keywords_list:
                kw_result = await self.db.execute(
                    select(Keyword).where(
                        Keyword.project_id == project.id,
                        Keyword.keyword.in_(cluster.keywords_list),
                    )
                )
                for kw in kw_result.scalars().all():
                    kw.intent = cluster_intent

        await self.db.flush()

        return {"keywords_classified": classified, "clusters_classified": len(clusters)}

    async def _classify_keyword(self, keyword: Keyword, project: Project) -> str:
        """Classify a single keyword's intent."""
        kw_lower = keyword.keyword.lower()

        # 1. Pattern-based classification
        scores = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            score = sum(1 for p in patterns if re.search(p, kw_lower))
            if score > 0:
                scores[intent] = score

        if scores:
            best_intent = max(scores, key=scores.get)
            if scores[best_intent] >= 2:
                return best_intent

        # 2. SERP-based classification
        serp_intent = await self._classify_from_serp(keyword.id)
        if serp_intent:
            return serp_intent

        # 3. Context-based heuristics
        cities = (project.target_cities or [])
        services = (project.services or [])

        has_city = any(city.lower() in kw_lower for city in cities)
        has_service = any(s.lower() in kw_lower for s in services)

        if has_city and has_service:
            return "local_transactional"
        if has_service:
            return "commercial"
        if any(q in kw_lower for q in ["was", "wie", "warum", "welche"]):
            return "informational"

        # 4. LLM classification for ambiguous cases
        if self.openai_key and "sk-" in self.openai_key:
            try:
                return await self._llm_classify(keyword.keyword)
            except Exception:
                pass

        return "commercial" if has_service else "informational"

    async def _classify_from_serp(self, keyword_id: str) -> Optional[str]:
        """Determine intent from SERP features."""
        result = await self.db.execute(
            select(SerpResult).where(
                SerpResult.keyword_id == keyword_id,
            ).limit(10)
        )
        serp_results = result.scalars().all()

        feature_counts = {}
        for sr in serp_results:
            if sr.serp_features:
                for feature, present in sr.serp_features.items():
                    if present and feature in self.SERP_INTENT_MAP:
                        intent = self.SERP_INTENT_MAP[feature]
                        feature_counts[intent] = feature_counts.get(intent, 0) + 1

        if feature_counts:
            return max(feature_counts, key=feature_counts.get)
        return None

    async def _classify_cluster(self, cluster: KeywordCluster, project: Project) -> str:
        """Classify intent for a keyword cluster based on its member keywords."""
        if not cluster.keywords_list:
            return "unknown"

        # Get intents of member keywords
        result = await self.db.execute(
            select(Keyword).where(
                Keyword.project_id == project.id,
                Keyword.keyword.in_(cluster.keywords_list),
            )
        )
        keywords = result.scalars().all()

        intent_counts = {}
        for kw in keywords:
            if kw.intent:
                intent_counts[kw.intent] = intent_counts.get(kw.intent, 0) + 1

        if intent_counts:
            return max(intent_counts, key=intent_counts.get)

        # Classify based on cluster name
        kw_lower = cluster.name.lower()
        for intent, patterns in self.INTENT_PATTERNS.items():
            if any(re.search(p, kw_lower) for p in patterns):
                return intent

        return "commercial"

    async def _llm_classify(self, keyword: str) -> str:
        """Use OpenAI to classify intent."""
        import openai
        client = openai.AsyncOpenAI(api_key=self.openai_key)

        prompt = f"""Classify the search intent of this keyword into exactly one category:
- local_transactional: Looking for local service provider
- commercial: Researching before buying/hiring
- informational: Looking for information/answers
- comparison: Comparing options
- problem_solution: Has a problem to solve
- brand: Searching for specific brand
- navigational: Looking for specific page

Keyword: "{keyword}"

Intent:"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.0,
        )
        intent = response.choices[0].message.content.strip().lower()
        return intent if intent in self.INTENT_PATTERNS else "commercial"
