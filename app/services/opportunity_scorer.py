"""
SEO opportunity scorer — cluster-first, type-diverse, city-merged.

Generates 20-35 meaningful, well-scored tasks instead of raw keyword tasks.
Decides per cluster: create_page, improve_page, add_section, add_faq,
add_internal_links, or ignore.
"""

import re
from typing import List, Dict, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Page, Keyword, KeywordCluster, ContentGap, SeoTask


# City names we strip from cluster names to get core topics
_KNOWN_CITIES = {
    "köln", "bonn", "düsseldorf", "leverkusen", "hürth", "frechen",
    "berlin", "hamburg", "münchen", "frankfurt", "stuttgart", "essen",
    "udon thani", "khon kaen", "nong khai", "sakon nakhon", "isaan",
    "bangkok", "chiang mai", "pattaya", "phuket",
    # Partial city fragments that get left after stripping
    "nong",  # from "nong khai"
    "khon",  # from "khon kaen"
}

# Generic single-word topics that should NOT become standalone pages
_GENERIC_TOPICS = {
    "lawyer", "anwalt", "app", "entwicklung", "hypnose", "therapie",
    "agentur", "service", "services", "beratung", "software",
    "marketing", "design", "consulting", "legal", "law", "firm",
}

# Words that indicate buying intent — these clusters are high value
_BUYING_MODIFIERS = {"kosten", "preise", "anwalt", "beratung", "preis", "honorar"}

# Max tasks total
_MAX_TASKS = 35


class OpportunityScorer:
    """Generates diverse, quality-filtered SEO tasks from clusters and gaps."""

    INTENT_SCORES = {
        "local_transactional": 1.0,
        "commercial": 0.9,
        "problem_solution": 0.85,
        "comparison": 0.6,
        "informational": 0.4,
        "brand": 0.7,
        "navigational": 0.3,
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self._existing_pages: Dict[str, Page] = {}
        self._page_urls: set = set()

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    async def score_all(self, project: Project) -> List[SeoTask]:
        await self._load_pages(project.id)

        all_tasks: List[dict] = []

        # 1. Cluster-based tasks (primary source)
        cluster_tasks = await self._generate_cluster_tasks(project)
        all_tasks.extend(cluster_tasks)

        # 2. Content gap tasks
        gap_tasks = await self._generate_gap_tasks(project)
        all_tasks.extend(gap_tasks)

        # 3. Technical SEO tasks
        tech_tasks = await self._generate_technical_tasks(project)
        all_tasks.extend(tech_tasks)

        # 4. Merge city-variant clusters
        all_tasks = self._merge_city_variants(all_tasks)

        # Score, prioritize, filter
        for t in all_tasks:
            t["priority_score"] = self._calculate_score(t)
            t["priority"] = self._to_priority(t["priority_score"])

        all_tasks.sort(key=lambda t: t["priority_score"], reverse=True)
        all_tasks = self._quality_filter(all_tasks)

        # Save to DB
        saved = []
        for t in all_tasks:
            task = SeoTask(
                project_id=project.id,
                page_id=t.get("page_id"),
                keyword_cluster_id=t.get("keyword_cluster_id"),
                title=t["title"],
                description=t.get("description"),
                reason=t.get("reason"),
                category=t["category"],
                priority=t["priority"],
                priority_score=t["priority_score"],
                checklist=t.get("checklist"),
                expected_impact=t.get("expected_impact"),
            )
            self.db.add(task)
            saved.append(task)

        await self.db.flush()
        return saved

    # ------------------------------------------------------------------
    # Load existing pages for matching
    # ------------------------------------------------------------------
    async def _load_pages(self, project_id: str) -> None:
        result = await self.db.execute(
            select(Page).where(Page.project_id == project_id, Page.is_own_site == True)
        )
        for p in result.scalars().all():
            self._existing_pages[p.url] = p
            self._page_urls.add(p.url.lower().rstrip("/"))

    # ------------------------------------------------------------------
    # Cluster task generation
    # ------------------------------------------------------------------
    async def _generate_cluster_tasks(self, project: Project) -> List[dict]:
        result = await self.db.execute(
            select(KeywordCluster).where(KeywordCluster.project_id == project.id)
        )
        clusters = result.scalars().all()

        tasks = []
        for cluster in clusters:
            intent = cluster.intent or "commercial"
            size = cluster.cluster_size or len(cluster.keywords_list or [])
            primary_kw = cluster.primary_keyword or ""

            # Determine action and generate task
            action, details = self._decide_cluster_action(cluster, primary_kw, size, intent, project)

            if action == "ignore":
                continue

            task = self._build_cluster_task(cluster, action, details, primary_kw, size, intent)
            if task:
                tasks.append(task)

        return tasks

    def _decide_cluster_action(
        self, cluster, primary_kw: str, size: int, intent: str, project: Project
    ) -> tuple:
        """Decide what action to take for a keyword cluster.

        Returns (action, details_dict).
        """
        # Generic single-word topics → ignore (too broad)
        core = self._extract_core_topic(cluster.name or primary_kw)
        if core.lower().strip() in _GENERIC_TOPICS:
            return ("ignore", {})

        # Very small clusters → ignore unless high intent
        if size <= 1 and intent in ("informational", "navigational"):
            return ("ignore", {})

        # Check if a page already targets this cluster
        matched_page = self._find_matching_page(cluster, primary_kw)

        # Clusters with buying modifiers → high value, create or improve
        has_buying = any(m in primary_kw.lower() for m in _BUYING_MODIFIERS)

        # Clusters that look like FAQ topics
        is_faq = self._is_faq_topic(primary_kw, cluster.name or "")

        # Clusters that look like internal link opportunities only
        is_nav = intent == "navigational"

        if matched_page:
            # Page exists → improve it
            if is_faq:
                return ("add_faq", {"page": matched_page, "faq_topic": primary_kw})
            return ("improve_page", {"page": matched_page})
        else:
            # No page exists
            if is_nav or size <= 1:
                return ("ignore", {})
            if is_faq:
                return ("add_faq", {"faq_topic": primary_kw})
            if has_buying or intent in ("local_transactional", "commercial", "problem_solution"):
                return ("create_page", {})
            if size >= 3:
                return ("add_section", {})
            return ("ignore", {})

    def _build_cluster_task(
        self, cluster, action: str, details: dict, primary_kw: str, size: int, intent: str
    ) -> Optional[dict]:
        """Build a task dict from cluster + action decision."""
        core_topic = self._extract_core_topic(cluster.name or primary_kw)
        base = {
            "keyword_cluster_id": cluster.id,
            "intent": intent,
            "cluster_size": size,
            "primary_keyword": primary_kw,
            "core_topic": core_topic,
        }

        if action == "create_page":
            base.update({
                "title": f"Create page: {core_topic}",
                "description": f"New dedicated page for '{core_topic}' targeting {size} related keywords.",
                "reason": f"No existing page covers this topic cluster ({size} keywords, {intent} intent)",
                "category": "content",
                "checklist": [
                    f"Write 800+ word content optimized for '{primary_kw}'",
                    "Include H2 sub-sections for each keyword variant",
                    "Add 5+ FAQ entries",
                    "Add internal links from homepage and service pages",
                    "Include local references (city, region) naturally",
                ],
                "expected_impact": f"Capture search traffic for {size} related keywords — estimate 50-200 monthly visits",
                "business_value": 9 if intent in ("local_transactional", "commercial") else 7,
                "action_type": "create",
            })
            return base

        elif action == "improve_page":
            page = details.get("page")
            page_title = page.title[:60] if page and page.title else core_topic
            base.update({
                "page_id": getattr(page, "id", None),
                "title": f"Improve: {page_title}",
                "description": f"Optimize existing page for cluster '{core_topic}' ({size} keywords).",
                "reason": f"Existing page can be improved for {size} keywords in this cluster",
                "category": "on_page",
                "checklist": [
                    f"Update title tag to include '{primary_kw}'",
                    "Rewrite meta description with primary keyword",
                    "Add missing H2 sub-sections for keyword variants",
                    "Improve internal linking from related pages",
                    "Add/refresh FAQ section",
                ],
                "expected_impact": f"Better rankings for {size} keywords with minimal effort",
                "business_value": 8,
                "action_type": "improve",
            })
            return base

        elif action == "add_section":
            base.update({
                "title": f"Add section: {core_topic}",
                "description": f"Add a dedicated section about '{core_topic}' to an existing page.",
                "reason": f"Small cluster ({size} keywords) — add as section instead of full page",
                "category": "content",
                "checklist": [
                    f"Add H2 section '{core_topic}' to the most relevant service page",
                    f"Include 2-3 paragraphs targeting '{primary_kw}'",
                    "Link from homepage or navigation if valuable",
                ],
                "expected_impact": f"Incremental coverage for {size} keyword variants",
                "business_value": 5,
                "action_type": "section",
            })
            return base

        elif action == "add_faq":
            faq_topic = details.get("faq_topic", core_topic)
            page = details.get("page")
            base.update({
                "page_id": getattr(page, "id", None) if page else None,
                "title": f"Add FAQ: {faq_topic}",
                "description": f"Add FAQ entries answering common questions about '{faq_topic}'.",
                "reason": "Question-based keywords detected — best served by FAQ content",
                "category": "content",
                "checklist": [
                    f"Write 5+ question/answer pairs about '{faq_topic}'",
                    "Use question-based H2 or H3 headings",
                    "Add FAQ schema markup",
                ],
                "expected_impact": "Capture featured snippets and 'People Also Ask' traffic",
                "business_value": 6,
                "action_type": "faq",
            })
            return base

        return None

    # ------------------------------------------------------------------
    # Content gap tasks
    # ------------------------------------------------------------------
    async def _generate_gap_tasks(self, project: Project) -> List[dict]:
        result = await self.db.execute(
            select(ContentGap)
            .where(ContentGap.project_id == project.id, ContentGap.status == "open")
            .order_by(ContentGap.severity.desc())
            .limit(12)
        )
        gaps = result.scalars().all()

        tasks = []
        for gap in gaps:
            sev = gap.severity
            tasks.append({
                "page_id": gap.page_id,
                "title": f"Fix gap: {gap.description[:80]}",
                "description": gap.description,
                "reason": f"Missing topic: {gap.gap_type} (severity: {sev})",
                "category": "content",
                "checklist": [gap.suggested_fix] if gap.suggested_fix else [f"Add content covering: {gap.description}"],
                "expected_impact": "Fill content gap — improve topical authority",
                "business_value": 8 if sev == "high" else 5 if sev == "medium" else 3,
                "action_type": "gap",
                "gap_severity": sev,
            })

        return tasks

    # ------------------------------------------------------------------
    # Technical tasks
    # ------------------------------------------------------------------
    async def _generate_technical_tasks(self, project: Project) -> List[dict]:
        pages = list(self._existing_pages.values())
        tasks = []

        # Missing titles
        without_title = [p for p in pages if not p.title and p.indexable]
        if without_title:
            tasks.append({
                "title": f"Add title tags to {len(without_title)} pages",
                "description": f"{len(without_title)} indexable pages are missing title tags.",
                "reason": "Missing title tags hurt CTR and rankings",
                "category": "technical",
                "checklist": [f"Add descriptive title to: {p.url}" for p in without_title[:5]],
                "expected_impact": f"Improved CTR for {len(without_title)} pages",
                "business_value": 9,
                "action_type": "technical",
            })

        # Missing meta descriptions  
        without_meta = [p for p in pages if not p.meta_description and p.indexable]
        if without_meta:
            tasks.append({
                "title": f"Add meta descriptions to {len(without_meta)} pages",
                "description": "Missing meta descriptions reduce click-through rates from search results.",
                "reason": "Meta descriptions improve SERP CTR",
                "category": "technical",
                "checklist": [f"Add 150-160 char meta description to: {p.url}" for p in without_meta[:5]],
                "expected_impact": f"Improved CTR for {len(without_meta)} pages",
                "business_value": 7,
                "action_type": "technical",
            })

        # Thin content pages
        thin_pages = [p for p in pages if p.word_count and p.word_count < 200 and p.indexable]
        if thin_pages:
            tasks.append({
                "title": f"Expand {len(thin_pages)} thin content pages",
                "description": f"{len(thin_pages)} pages have fewer than 200 words — search engines may consider them low quality.",
                "reason": "Thin content pages risk being devalued by search engines",
                "category": "content",
                "checklist": [f"Expand content on: {p.url} (currently {p.word_count} words)" for p in thin_pages[:5]],
                "expected_impact": "Improved content quality signals",
                "business_value": 8,
                "action_type": "technical",
            })

        return tasks

    # ------------------------------------------------------------------
    # City variant merging
    # ------------------------------------------------------------------
    def _merge_city_variants(self, tasks: List[dict]) -> List[dict]:
        """Merge tasks that differ only by city into one strategic task."""
        # Group by core topic (without city)
        groups: Dict[str, List[dict]] = {}
        for t in tasks:
            core = self._extract_core_topic(t.get("core_topic", t.get("title", "")))
            groups.setdefault(core, []).append(t)

        merged = []
        for core, group in groups.items():
            if len(group) == 1:
                merged.extend(group)
                continue

            # Pick the best one (highest score components) as representative
            best = max(group, key=lambda t: (
                t.get("business_value", 5),
                t.get("cluster_size", 1),
                t.get("intent_score", 0.5),
            ))

            # If the best is already "create_page", use that title
            # Otherwise note merged cities
            cities = set()
            for t in group:
                pk = t.get("primary_keyword", "")
                for city in _KNOWN_CITIES:
                    if city in pk.lower():
                        cities.add(city)

            if best.get("action_type") == "create" and cities:
                city_list = ", ".join(sorted(cities)[:4])
                best["title"] = f"Create page: {core} ({city_list})"
                total_size = sum(t.get("cluster_size", 1) for t in group)
                best["cluster_size"] = min(total_size, 30)
                best["description"] = f"Strategic page for '{core}' covering {len(cities)} cities — {best['cluster_size']} keyword variants"

            merged.append(best)

        return merged

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_core_topic(self, name: str) -> str:
        """Extract clean topic name by stripping known cities and filler words."""
        name = name.lower().strip()
        # Remove known cities
        for city in sorted(_KNOWN_CITIES, key=len, reverse=True):
            name = re.sub(rf"\b{re.escape(city)}\b", "", name)
        # Clean up
        name = re.sub(r"\s+", " ", name).strip().strip("-").strip(",")
        if not name or len(name) < 3:
            return "untitled topic"
        return name[:80]

    def _find_matching_page(self, cluster, primary_kw: str) -> Optional[Page]:
        """Find an existing page that targets this cluster."""
        if cluster.target_page_url:
            return self._existing_pages.get(cluster.target_page_url)

        # Fuzzy match: check if any page title/URL contains the primary keyword
        kw_parts = set(primary_kw.lower().split())
        for url, page in self._existing_pages.items():
            url_lower = url.lower()
            title_lower = (page.title or "").lower()
            combined = f"{url_lower} {title_lower}"
            if any(part in combined for part in kw_parts if len(part) > 3):
                return page

        return None

    def _is_faq_topic(self, keyword: str, cluster_name: str) -> bool:
        """Check if this cluster looks like FAQ/tutorial content."""
        question_starters = (
            "was ", "wie ", "warum ", "welche ", "wann ", "wo ", "wer ",
            "ist ", "kann ", "hat ", "does ", "how ", "why ", "what ",
            "when ", "where ", "who ", "can ", "is ", "are ", "do ",
            "kosten ", "preis ", "preise ",
        )
        kw_lower = keyword.lower()
        name_lower = cluster_name.lower()
        combined = f"{kw_lower} {name_lower}"
        return any(combined.startswith(q) for q in question_starters)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    def _calculate_score(self, t: dict) -> float:
        """Calculate priority score with better differentiation."""
        bv = t.get("business_value", 5) / 10.0  # 0.3 - 1.0
        intent = t.get("intent_score", 0.5) if "intent_score" in t else self.INTENT_SCORES.get(t.get("intent", "informational"), 0.5)
        size = min(t.get("cluster_size", 1), 20)
        size_boost = 0.5 + (size / 20.0) * 0.5  # 0.5 - 1.0

        # Action type weight
        action_weights = {
            "create": 1.0, "improve": 0.9, "gap": 0.85,
            "technical": 0.8, "faq": 0.65, "section": 0.5,
        }
        action_w = action_weights.get(t.get("action_type", "create"), 0.7)

        # Gap severity
        gap_sev = t.get("gap_severity", "")
        sev_boost = 1.0 if gap_sev == "high" else 0.8 if gap_sev == "medium" else 0.6

        # Combine with wider spread
        raw = bv * intent * size_boost * action_w * sev_boost
        # Spread to 15-95 range
        score = 15 + raw * 80
        return round(score, 1)

    def _to_priority(self, score: float) -> str:
        if score >= 70:
            return "critical"
        if score >= 45:
            return "high"
        if score >= 25:
            return "medium"
        return "low"

    # ------------------------------------------------------------------
    # Quality filter
    # ------------------------------------------------------------------
    def _quality_filter(self, tasks: List[dict]) -> List[dict]:
        """Filter to only meaningful, non-duplicate tasks. Max 35."""
        # Remove low-priority
        filtered = [t for t in tasks if t["priority"] in ("critical", "high", "medium")]

        # Deduplicate by normalized title
        seen = set()
        unique = []
        for t in filtered:
            key = re.sub(r"[^a-z0-9]", "", t["title"].lower())
            if key not in seen and len(key) > 5:
                seen.add(key)
                unique.append(t)

        # Sort by score
        unique.sort(key=lambda t: t["priority_score"], reverse=True)

        # Limit
        return unique[:_MAX_TASKS]
