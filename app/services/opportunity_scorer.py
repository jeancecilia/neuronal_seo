"""
SEO opportunity scoring engine.
Scores each SEO task by business value, intent, opportunity, and feasibility.
Generates prioritized task list.
"""

from typing import List, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Project,
    Page,
    Keyword,
    KeywordCluster,
    ContentGap,
    SerpResult,
    SeoTask,
)


class OpportunityScorer:
    """
    Scores SEO opportunities and generates prioritized task tickets.
    Formula: priority = business_value × intent_score × opportunity × feasibility
    """

    INTENT_SCORES = {
        "local_transactional": 1.0,
        "commercial": 0.9,
        "problem_solution": 0.85,
        "comparison": 0.6,
        "informational": 0.4,
        "brand": 0.7,
        "navigational": 0.3,
        "support": 0.35,
        "unknown": 0.5,
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def score_all(self, project: Project) -> List[SeoTask]:
        """Generate and score all SEO opportunities for a project."""
        all_tasks = []

        # 1. Tasks from content gaps
        gap_tasks = await self._generate_gap_tasks(project)
        all_tasks.extend(gap_tasks)

        # 2. Tasks from keyword clusters
        cluster_tasks = await self._generate_cluster_tasks(project)
        all_tasks.extend(cluster_tasks)

        # 3. Technical SEO tasks
        tech_tasks = await self._generate_technical_tasks(project)
        all_tasks.extend(tech_tasks)

        # Score all tasks
        for task_data in all_tasks:
            score = self._calculate_priority_score(task_data)
            task_data["priority_score"] = score
            task_data["priority"] = self._score_to_priority(score)

        # Sort by priority score
        all_tasks.sort(key=lambda t: t["priority_score"], reverse=True)

        # Save to database
        saved_tasks = []
        for task_data in all_tasks:
            task = SeoTask(
                project_id=project.id,
                page_id=task_data.get("page_id"),
                keyword_cluster_id=task_data.get("keyword_cluster_id"),
                title=task_data["title"],
                description=task_data.get("description"),
                reason=task_data.get("reason"),
                category=task_data["category"],
                priority=task_data["priority"],
                priority_score=task_data["priority_score"],
                checklist=task_data.get("checklist"),
                expected_impact=task_data.get("expected_impact"),
            )
            self.db.add(task)
            saved_tasks.append(task)

        await self.db.flush()
        return saved_tasks

    async def _generate_gap_tasks(self, project: Project) -> List[dict]:
        """Generate tasks from content gaps."""
        result = await self.db.execute(
            select(ContentGap).where(
                ContentGap.project_id == project.id,
                ContentGap.status == "open",
            )
        )
        gaps = result.scalars().all()

        tasks = []
        for gap in gaps:
            intent = "commercial"  # Default
            if gap.page_id:
                page_result = await self.db.execute(
                    select(Page).where(Page.id == gap.page_id)
                )
                page = page_result.scalar_one_or_none()
                if page:
                    # Get cluster intent for scoring
                    pass

            tasks.append({
                "page_id": gap.page_id,
                "keyword_cluster_id": gap.keyword_cluster_id,
                "title": f"Fix: {gap.description}",
                "description": gap.description,
                "reason": f"Content gap detected: {gap.gap_type}",
                "category": "content",
                "checklist": [gap.suggested_fix] if gap.suggested_fix else [],
                "expected_impact": "Improved topical coverage and relevance",
                "business_value": 7 if gap.severity == "high" else 4,
                "intent_score": self.INTENT_SCORES.get(intent, 0.5),
                "opportunity_score": 0.8 if gap.severity == "high" else 0.5,
                "feasibility_score": 0.9,  # Content fixes are usually feasible
                "priority_score": 0.0,
            })

        return tasks

    async def _generate_cluster_tasks(self, project: Project) -> List[dict]:
        """Generate tasks from keyword cluster actions."""
        result = await self.db.execute(
            select(KeywordCluster).where(KeywordCluster.project_id == project.id)
        )
        clusters = result.scalars().all()

        tasks = []
        for cluster in clusters:
            intent = cluster.intent or "commercial"
            intent_score = self.INTENT_SCORES.get(intent, 0.5)

            if cluster.action == "create_new":
                tasks.append({
                    "keyword_cluster_id": cluster.id,
                    "title": f"Create new page for: {cluster.name}",
                    "description": f"Create a new {intent} page targeting keyword cluster '{cluster.name}' ({cluster.cluster_size} keywords)",
                    "reason": f"No existing page covers this keyword cluster ({cluster.cluster_size} keywords)",
                    "category": "content",
                    "checklist": [
                        f"Write {intent} page content for target keywords",
                        f"Include all keywords: {', '.join(cluster.keywords_list[:5])}",
                        "Add FAQ section",
                        "Add internal links from related pages",
                        "Add schema markup",
                    ],
                    "expected_impact": f"Capture search traffic for {cluster.cluster_size} related keywords",
                    "business_value": 8 if intent in ("local_transactional", "commercial") else 5,
                    "intent_score": intent_score,
                    "opportunity_score": 0.85,
                    "feasibility_score": 0.8,
                    "priority_score": 0.0,
                })

            elif cluster.action == "improve_existing":
                tasks.append({
                    "keyword_cluster_id": cluster.id,
                    "title": f"Improve page for cluster: {cluster.name}",
                    "description": f"Optimize existing page {cluster.target_page_url} for the '{cluster.name}' keyword cluster",
                    "reason": f"Existing page {cluster.target_page_url} needs optimization for this cluster",
                    "category": "on_page",
                    "checklist": [
                        f"Optimize title tag for: {cluster.primary_keyword}",
                        f"Include secondary keywords: {', '.join(cluster.keywords_list[:3])}",
                        "Improve heading structure",
                        "Update meta description",
                        "Add missing content sections",
                    ],
                    "expected_impact": f"Better rankings for {cluster.cluster_size} keywords",
                    "business_value": 7,
                    "intent_score": intent_score,
                    "opportunity_score": 0.7,
                    "feasibility_score": 0.9,
                    "priority_score": 0.0,
                })

        return tasks

    async def _generate_technical_tasks(self, project: Project) -> List[dict]:
        """Generate technical SEO tasks."""
        result = await self.db.execute(
            select(Page).where(
                Page.project_id == project.id,
                Page.is_own_site == True,
            )
        )
        pages = result.scalars().all()

        tasks = []

        # Check for missing title tags
        pages_without_title = [p for p in pages if not p.title]
        if pages_without_title:
            tasks.append({
                "title": f"Add missing title tags to {len(pages_without_title)} pages",
                "description": f"{len(pages_without_title)} pages have no title tag",
                "reason": "Missing title tags hurt SEO",
                "category": "technical",
                "checklist": [f"Add title tag to: {p.url}" for p in pages_without_title[:5]],
                "expected_impact": "Improved CTR and rankings",
                "business_value": 9,
                "intent_score": 1.0,
                "opportunity_score": 0.95,
                "feasibility_score": 0.95,
                "priority_score": 0.0,
            })

        # Check for missing meta descriptions
        pages_without_meta = [p for p in pages if not p.meta_description and p.indexable]
        if pages_without_meta:
            tasks.append({
                "title": f"Add meta descriptions to {len(pages_without_meta)} pages",
                "description": f"{len(pages_without_meta)} indexable pages have no meta description",
                "reason": "Missing meta descriptions reduce CTR",
                "category": "technical",
                "checklist": [f"Add meta description to: {p.url}" for p in pages_without_meta[:5]],
                "expected_impact": "Improved CTR from search results",
                "business_value": 8,
                "intent_score": 0.9,
                "opportunity_score": 0.8,
                "feasibility_score": 0.95,
                "priority_score": 0.0,
            })

        # Check for noindex pages that should be indexed
        for page in pages:
            if not page.indexable and page.content and (page.word_count or 0) > 200:
                tasks.append({
                    "page_id": page.id,
                    "title": f"Review noindex status for: {page.url}",
                    "description": f"Page {page.url} has {page.word_count} words but is set to noindex",
                    "reason": "Valuable content may be blocked from indexing",
                    "category": "technical",
                    "checklist": [
                        f"Review why {page.url} is noindex",
                        "Change to index if intentional content exists",
                    ],
                    "expected_impact": "More pages indexed and ranking",
                    "business_value": 6,
                    "intent_score": 0.7,
                    "opportunity_score": 0.6,
                    "feasibility_score": 0.95,
                    "priority_score": 0.0,
                })
                break  # Only flag one to avoid spam

        return tasks

    def _calculate_priority_score(self, task_data: dict) -> float:
        """Calculate priority score: business_value × intent × opportunity × feasibility."""
        bv = task_data.get("business_value", 5) / 10.0  # Normalize to 0-1
        intent = task_data.get("intent_score", 0.5)
        opportunity = task_data.get("opportunity_score", 0.5)
        feasibility = task_data.get("feasibility_score", 0.5)

        score = bv * intent * opportunity * feasibility * 100
        return round(score, 1)

    def _score_to_priority(self, score: float) -> str:
        """Convert numeric score to priority label."""
        if score >= 70:
            return "critical"
        elif score >= 40:
            return "high"
        elif score >= 20:
            return "medium"
        else:
            return "low"
