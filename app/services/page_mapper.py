"""
Page map generator that decides what should happen with each keyword cluster:
create new page, improve existing page, merge pages, noindex, etc.
"""

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Page, Keyword, KeywordCluster


class PageMapper:
    """
    Maps keyword clusters to target pages and decides actions.
    Actions: create_new, improve_existing, merge, noindex, no_action
    """

    # Intent to page type mapping
    INTENT_PAGE_TYPE = {
        "local_transactional": "service_page",
        "commercial": "landing_page",
        "informational": "blog_post",
        "comparison": "article",
        "problem_solution": "service_page",
        "brand": "home_page",
        "navigational": "landing_page",
        "support": "faq_page",
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def map_clusters(self, project: Project) -> List[Dict]:
        """Map all keyword clusters to target pages with actions."""
        result = await self.db.execute(
            select(KeywordCluster).where(KeywordCluster.project_id == project.id)
        )
        clusters = result.scalars().all()

        # Get existing pages
        result = await self.db.execute(
            select(Page).where(
                Page.project_id == project.id,
                Page.is_own_site == True,
            )
        )
        existing_pages = result.scalars().all()

        mappings = []
        for cluster in clusters:
            mapping = await self._map_single_cluster(cluster, existing_pages, project)
            if mapping:
                # Update cluster in database
                cluster.action = mapping["action"]
                cluster.target_page_url = mapping.get("target_url")
                mappings.append(mapping)

        await self.db.flush()
        return mappings

    async def _map_single_cluster(
        self,
        cluster: KeywordCluster,
        existing_pages: List[Page],
        project: Project,
    ) -> Optional[Dict]:
        """Determine the best action for a single keyword cluster."""
        cluster_name = cluster.name
        primary_kw = cluster.primary_keyword or cluster_name
        intent = cluster.intent or "commercial"

        # Try to find matching existing page
        best_match = await self._find_matching_page(cluster, existing_pages, project)

        if best_match:
            match_score = best_match["score"]
            target_url = best_match["page"].url

            if match_score > 0.8:
                action = "improve_existing"
                reason = f"Strong match with existing page {target_url}"
            elif match_score > 0.5:
                action = "improve_existing"
                reason = f"Moderate match with {target_url} - needs optimization"
            else:
                action = "create_new"
                target_url = self._generate_target_url(primary_kw, intent, project)
                reason = "Weak match with existing pages - create dedicated page"
        else:
            action = "create_new"
            target_url = self._generate_target_url(primary_kw, intent, project)
            reason = "No existing page covers this cluster topic"

        # Determine page type based on intent
        page_type = self.INTENT_PAGE_TYPE.get(intent, "landing_page")

        return {
            "cluster_id": cluster.id,
            "cluster_name": cluster_name,
            "primary_keyword": primary_kw,
            "intent": intent,
            "action": action,
            "target_url": target_url,
            "page_type": page_type,
            "reason": reason,
            "cluster_size": cluster.cluster_size,
        }

    async def _find_matching_page(
        self,
        cluster: KeywordCluster,
        existing_pages: List[Page],
        project: Project,
    ) -> Optional[Dict]:
        """Find the best matching existing page for a cluster."""
        if not cluster.keywords_list:
            return None

        best_score = 0
        best_page = None

        for page in existing_pages:
            # Simple text overlap scoring
            score = self._calculate_page_match_score(cluster, page)
            if score > best_score:
                best_score = score
                best_page = page

        if best_page and best_score > 0.2:
            return {"page": best_page, "score": best_score}
        return None

    def _calculate_page_match_score(self, cluster: KeywordCluster, page: Page) -> float:
        """Calculate how well an existing page matches a keyword cluster."""
        page_text = f"{page.title or ''} {page.h1 or ''} {' '.join(page.h2 or [])} {page.url}".lower()
        cluster_keywords = [kw.lower() for kw in (cluster.keywords_list or [])]

        if not page_text or not cluster_keywords:
            return 0.0

        # Count keyword matches in page content
        total_words = set()
        for kw in cluster_keywords:
            total_words.update(kw.split())

        matches = 0
        for word in total_words:
            if word in page_text:
                matches += 1

        if not total_words:
            return 0.0

        return matches / len(total_words)

    def _generate_target_url(self, keyword: str, intent: str, project: Project) -> str:
        """Generate a URL slug from a keyword and intent."""
        slug = keyword.lower().replace(" ", "-").replace(".", "").replace(",", "")
        # Remove special chars
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        slug = slug.strip("-")[:100]

        if intent in ("informational", "comparison"):
            return f"/blog/{slug}" if "blog" not in slug else f"/{slug}"
        else:
            return f"/{slug}"
