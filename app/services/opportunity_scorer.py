"""
SEO opportunity scorer — cluster-first, quality-filtered.
Generates 20-35 meaningful tasks instead of hundreds of raw keyword tasks.
"""

from typing import List, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Page, Keyword, KeywordCluster, ContentGap, SeoTask


class OpportunityScorer:

    INTENT_SCORES = {
        "local_transactional": 1.0, "commercial": 0.9, "problem_solution": 0.85,
        "comparison": 0.6, "informational": 0.4, "brand": 0.7, "navigational": 0.3,
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def score_all(self, project: Project) -> List[SeoTask]:
        all_tasks = []

        # 1. Cluster-based tasks (the main source)
        cluster_tasks = await self._generate_cluster_tasks(project)
        all_tasks.extend(cluster_tasks)

        # 2. Content gap tasks (from gap detection)
        gap_tasks = await self._generate_gap_tasks(project)
        all_tasks.extend(gap_tasks)

        # 3. Technical SEO tasks (limited)
        tech_tasks = await self._generate_technical_tasks(project)
        all_tasks.extend(tech_tasks)

        # Score and filter
        for t in all_tasks:
            t["priority_score"] = self._calculate_score(t)
            t["priority"] = self._to_priority(t["priority_score"])

        # Sort by score, keep only top quality tasks
        all_tasks.sort(key=lambda t: t["priority_score"], reverse=True)
        all_tasks = self._quality_filter(all_tasks)

        # Save
        saved = []
        for t in all_tasks:
            task = SeoTask(
                project_id=project.id, page_id=t.get("page_id"),
                keyword_cluster_id=t.get("keyword_cluster_id"),
                title=t["title"], description=t.get("description"),
                reason=t.get("reason"), category=t["category"],
                priority=t["priority"], priority_score=t["priority_score"],
                checklist=t.get("checklist"), expected_impact=t.get("expected_impact"),
            )
            self.db.add(task)
            saved.append(task)

        await self.db.flush()
        return saved

    async def _generate_cluster_tasks(self, project: Project) -> List[dict]:
        """Generate one task per keyword cluster (not per keyword)."""
        result = await self.db.execute(
            select(KeywordCluster).where(KeywordCluster.project_id == project.id)
        )
        clusters = result.scalars().all()

        tasks = []
        for cluster in clusters:
            intent = cluster.intent or "commercial"
            intent_score = self.INTENT_SCORES.get(intent, 0.5)
            size = cluster.cluster_size or len(cluster.keywords_list or [])

            # Merge city variants — one task per cluster
            if cluster.action == "create_new":
                tasks.append({
                    "keyword_cluster_id": cluster.id,
                    "title": f"Create page: {cluster.name}",
                    "description": f"New {intent} page for cluster '{cluster.name}' ({size} keywords)",
                    "reason": f"No existing page covers this topic cluster",
                    "category": "content",
                    "checklist": [
                        f"Write content targeting: {cluster.primary_keyword}",
                        "Add FAQ section with 5+ questions",
                        "Add internal links from related pages",
                    ],
                    "expected_impact": f"Capture search traffic for {size} related keywords",
                    "business_value": 8 if intent in ("local_transactional", "commercial") else 5,
                    "intent_score": intent_score, "opportunity_score": 0.85,
                    "feasibility_score": 0.8,
                    "cluster_size": size,
                })
            elif cluster.action == "improve_existing":
                tasks.append({
                    "keyword_cluster_id": cluster.id,
                    "title": f"Optimize: {cluster.name}",
                    "description": f"Improve {cluster.target_page_url} for cluster '{cluster.name}'",
                    "reason": f"Existing page needs optimization for {size} keywords",
                    "category": "on_page",
                    "checklist": [
                        f"Optimize title for: {cluster.primary_keyword}",
                        "Update meta description",
                        "Improve heading structure",
                    ],
                    "expected_impact": f"Better rankings for {size} keywords",
                    "business_value": 7, "intent_score": intent_score,
                    "opportunity_score": 0.7, "feasibility_score": 0.9,
                    "cluster_size": size,
                })

        return tasks

    async def _generate_gap_tasks(self, project: Project) -> List[dict]:
        """Tasks from content gaps — limited to top gaps."""
        result = await self.db.execute(
            select(ContentGap).where(
                ContentGap.project_id == project.id, ContentGap.status == "open"
            ).order_by(ContentGap.severity.desc()).limit(15)
        )
        gaps = result.scalars().all()

        tasks = []
        for gap in gaps:
            sev = gap.severity
            tasks.append({
                "page_id": gap.page_id,
                "title": f"Fix: {gap.description[:80]}",
                "description": gap.description,
                "reason": f"Content gap: {gap.gap_type}",
                "category": "content",
                "checklist": [gap.suggested_fix] if gap.suggested_fix else [],
                "expected_impact": "Improved topical coverage",
                "business_value": 7 if sev == "high" else 4,
                "intent_score": 0.7, "opportunity_score": 0.8 if sev == "high" else 0.5,
                "feasibility_score": 0.9,
                "gap_severity": sev,
            })

        return tasks

    async def _generate_technical_tasks(self, project: Project) -> List[dict]:
        """Limited technical tasks."""
        result = await self.db.execute(
            select(Page).where(Page.project_id == project.id, Page.is_own_site == True)
        )
        pages = result.scalars().all()

        tasks = []
        without_title = [p for p in pages if not p.title and p.indexable]
        if without_title:
            tasks.append({
                "title": f"Add title tags to {len(without_title)} pages",
                "description": f"{len(without_title)} pages missing title tags",
                "category": "technical",
                "checklist": [f"Add title to: {p.url}" for p in without_title[:3]],
                "expected_impact": "Improved CTR",
                "business_value": 9, "intent_score": 1.0,
                "opportunity_score": 0.95, "feasibility_score": 0.95,
            })

        without_meta = [p for p in pages if not p.meta_description and p.indexable]
        if without_meta:
            tasks.append({
                "title": f"Add meta descriptions to {len(without_meta)} pages",
                "description": "Missing meta descriptions reduce CTR",
                "category": "technical",
                "checklist": [f"Add meta to: {p.url}" for p in without_meta[:3]],
                "expected_impact": "Improved CTR",
                "business_value": 8, "intent_score": 0.9,
                "opportunity_score": 0.8, "feasibility_score": 0.95,
            })

        return tasks

    def _calculate_score(self, t: dict) -> float:
        bv = t.get("business_value", 5) / 10.0
        intent = t.get("intent_score", 0.5)
        opp = t.get("opportunity_score", 0.5)
        feas = t.get("feasibility_score", 0.5)
        # Boost larger clusters
        size_boost = min(t.get("cluster_size", 1) / 5.0, 1.5)
        return round(bv * intent * opp * feas * size_boost * 100, 1)

    def _to_priority(self, score: float) -> str:
        if score >= 70: return "critical"
        if score >= 40: return "high"
        if score >= 20: return "medium"
        return "low"

    def _quality_filter(self, tasks: List[dict]) -> List[dict]:
        """Keep only meaningful tasks, limit to ~25-35."""
        # Remove low-priority
        filtered = [t for t in tasks if t["priority"] in ("critical", "high", "medium")]
        # Deduplicate by title
        seen = set()
        unique = []
        for t in filtered:
            key = t["title"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(t)
        # Limit
        return unique[:35]
