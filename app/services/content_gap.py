"""
Content gap detection engine that compares your pages against competitors
and keyword clusters to find missing sections, entities, FAQs, and trust signals.
"""

from typing import List, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Project,
    Page,
    PageChunk,
    Keyword,
    KeywordCluster,
    CompetitorPage,
    ContentGap,
)


class ContentGapDetector:
    """
    Detects content gaps by comparing your pages against top-ranking competitors.
    Identifies missing sections, entities, FAQs, trust signals, and more.
    """

    ESSENTIAL_SECTIONS = {
        "service_page": [
            "pricing", "process", "benefits", "FAQ", "CTA",
            "testimonials", "case_studies", "local_references",
            "about_team", "technology_stack",
        ],
        "blog_post": [
            "introduction", "main_content", "examples",
            "conclusion", "FAQ", "related_posts", "CTA",
        ],
        "landing_page": [
            "hero_section", "benefits", "features",
            "social_proof", "pricing", "FAQ", "CTA",
        ],
    }

    COMPETITOR_MUST_HAVES = [
        "pricing", "process", "faq", "testimonials",
        "case_studies", "local_references", "trust_signals",
        "cta", "schema_markup",
    ]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def detect_gaps(self, project: Project) -> List[ContentGap]:
        """Detect all content gaps for a project."""
        all_gaps = []

        # Get own pages
        result = await self.db.execute(
            select(Page).where(
                Page.project_id == project.id,
                Page.is_own_site == True,
            )
        )
        own_pages = result.scalars().all()

        # Get competitor pages
        result = await self.db.execute(
            select(CompetitorPage).where(
                CompetitorPage.project_id == project.id,
            )
        )
        competitor_pages = result.scalars().all()

        # Get keyword clusters
        result = await self.db.execute(
            select(KeywordCluster).where(
                KeywordCluster.project_id == project.id,
            )
        )
        clusters = result.scalars().all()

        # Detect gaps for each own page
        for page in own_pages:
            # Find matching cluster
            matching_cluster = self._find_matching_cluster(page, clusters)
            page_gaps = await self._detect_page_gaps(
                page, competitor_pages, matching_cluster, project
            )
            all_gaps.extend(page_gaps)

        # Detect missing pages (clusters without pages)
        cluster_gaps = await self._detect_missing_page_gaps(clusters, own_pages, project)
        all_gaps.extend(cluster_gaps)

        # Save gaps to database
        saved_gaps = []
        for gap_data in all_gaps:
            gap = ContentGap(
                project_id=project.id,
                page_id=gap_data.get("page_id"),
                keyword_cluster_id=gap_data.get("keyword_cluster_id"),
                gap_type=gap_data["gap_type"],
                description=gap_data["description"],
                severity=gap_data.get("severity", "medium"),
                suggested_fix=gap_data.get("suggested_fix"),
                competitors_have=gap_data.get("competitors_have"),
            )
            self.db.add(gap)
            saved_gaps.append(gap)

        await self.db.flush()
        return saved_gaps

    async def _detect_page_gaps(
        self,
        page: Page,
        competitor_pages: List[CompetitorPage],
        cluster: Optional[KeywordCluster],
        project: Project,
    ) -> List[dict]:
        """Detect content gaps for a single page."""
        gaps = []
        page_type = page.page_type or "landing_page"

        # 1. Essential section gaps
        essential = self.ESSENTIAL_SECTIONS.get(page_type, self.ESSENTIAL_SECTIONS["landing_page"])
        for section in essential:
            if not self._has_section(page, section):
                # Check if competitors have this section
                comps_with = [
                    cp.url for cp in competitor_pages[:5]
                    if self._competitor_has_section(cp, section)
                ]
                gaps.append({
                    "page_id": page.id,
                    "gap_type": f"missing_{section}",
                    "description": f"Page is missing '{section}' section",
                    "severity": "high" if section in ["pricing", "FAQ"] else "medium",
                    "suggested_fix": f"Add a '{section}' section to the page",
                    "competitors_have": comps_with[:3],
                })

        # 2. Content thinness
        if page.word_count and page.word_count < 300:
            avg_comp_words = sum(
                cp.word_count or 0 for cp in competitor_pages[:5]
            ) / max(len(competitor_pages[:5]), 1)
            if avg_comp_words > 500:
                gaps.append({
                    "page_id": page.id,
                    "gap_type": "thin_content",
                    "description": f"Page has {page.word_count} words vs competitor average of {int(avg_comp_words)}",
                    "severity": "high",
                    "suggested_fix": f"Expand content to at least {int(avg_comp_words * 0.8)} words",
                })

        # 3. FAQ gaps
        if not any("faq" in (h.lower() if h else "") for h in (page.h2 or [])):
            comps_with_faq = [
                cp.url for cp in competitor_pages[:5]
                if cp.faqs and len(cp.faqs) > 0
            ]
            if comps_with_faq:
                gaps.append({
                    "page_id": page.id,
                    "gap_type": "missing_faq",
                    "description": "Page lacks FAQ section - competitors include FAQs",
                    "severity": "medium",
                    "suggested_fix": "Add FAQ section with 5+ questions",
                    "competitors_have": comps_with_faq[:3],
                })

        # 4. Trust signal gaps
        comps_with_trust = [
            cp.url for cp in competitor_pages[:5] if cp.has_trust_signals
        ]
        if comps_with_trust:
            # Check own page for trust signals
            own_content = (page.content or "").lower()
            trust_words = ["testimonial", "bewertung", "review", "kundenstimmen",
                          "referenz", "zertifiziert", "auszeichnung"]
            if not any(tw in own_content for tw in trust_words):
                gaps.append({
                    "page_id": page.id,
                    "gap_type": "missing_trust",
                    "description": "Page lacks trust signals that competitors include",
                    "severity": "high",
                    "suggested_fix": "Add testimonials, reviews, or certifications",
                    "competitors_have": comps_with_trust[:3],
                })

        # 5. Schema markup gaps
        if not page.schema_markup:
            comps_with_schema = [
                cp.url for cp in competitor_pages[:5]
                if cp.schema_types and len(cp.schema_types) > 0
            ]
            if comps_with_schema:
                gaps.append({
                    "page_id": page.id,
                    "gap_type": "missing_schema",
                    "description": "Page has no schema markup - competitors use structured data",
                    "severity": "medium",
                    "suggested_fix": "Add LocalBusiness, Service, or FAQ schema",
                    "competitors_have": comps_with_schema[:3],
                })

        return gaps

    async def _detect_missing_page_gaps(
        self,
        clusters: List[KeywordCluster],
        own_pages: List[Page],
        project: Project,
    ) -> List[dict]:
        """Detect clusters that need new pages."""
        gaps = []

        for cluster in clusters:
            if cluster.action == "create_new":
                gaps.append({
                    "keyword_cluster_id": cluster.id,
                    "gap_type": "missing_page",
                    "description": f"No page exists for keyword cluster: {cluster.name}",
                    "severity": "high",
                    "suggested_fix": f"Create new {cluster.intent or 'landing'} page: {cluster.target_page_url or self._suggest_url(cluster.name)}",
                })

        return gaps

    def _has_section(self, page: Page, section: str) -> bool:
        """Check if a page has a specific section type."""
        content = (page.content or "").lower()
        headings = [h.lower() for h in (page.h2 or []) + (page.h3 or [])]

        section_map = {
            "pricing": ["preis", "kosten", "pricing", "investition", "angebot"],
            "faq": ["faq", "fragen", "häufig", "questions"],
            "testimonials": ["testimonial", "bewertung", "kundenstimmen", "referenz", "erfahrung"],
            "process": ["prozess", "ablauf", "process", "vorgehen", "schritte"],
            "benefits": ["vorteile", "benefits", "warum", "gründe"],
            "case_studies": ["fallstudie", "case study", "projekt", "portfolio"],
            "cta": ["jetzt", "kontakt", "anfragen", "beratung", "termin"],
            "local_references": ["köln", "berlin", "lokal", "standort", "region"],
            "about_team": ["team", "über uns", "about", "wer wir sind"],
            "technology_stack": ["technologie", "tech stack", "flutter", "react"],
            "introduction": ["was ist", "einführung", "überblick"],
            "examples": ["beispiel", "example", "use case", "anwendung"],
        }

        keywords = section_map.get(section, [section.lower()])
        text_match = any(kw in content for kw in keywords)
        heading_match = any(any(kw in h for kw in keywords) for h in headings)

        return text_match or heading_match

    def _competitor_has_section(self, cp: CompetitorPage, section: str) -> bool:
        """Check if a competitor page has a specific section."""
        if section == "faq":
            return bool(cp.faqs and len(cp.faqs) > 0)
        if section == "pricing":
            return cp.has_pricing
        if section == "trust_signals":
            return cp.has_trust_signals
        if section == "case_studies":
            return cp.has_case_studies
        if section == "local_references":
            return cp.has_local_refs
        if section == "cta":
            return cp.has_cta
        if section == "schema_markup":
            return bool(cp.schema_types and len(cp.schema_types) > 0)

        # Default: check content
        content = (cp.content or "").lower()
        return section.lower() in content

    def _find_matching_cluster(
        self,
        page: Page,
        clusters: List[KeywordCluster],
    ) -> Optional[KeywordCluster]:
        """Find the best matching cluster for a page."""
        page_text = f"{page.title or ''} {page.h1 or ''} {' '.join(page.h2 or [])}".lower()

        best_score = 0
        best_cluster = None

        for cluster in clusters:
            if not cluster.keywords_list:
                continue
            score = sum(
                1 for kw in cluster.keywords_list
                if any(word in page_text for word in kw.lower().split())
            )
            if score > best_score:
                best_score = score
                best_cluster = cluster

        return best_cluster if best_score >= 2 else None

    def _suggest_url(self, cluster_name: str) -> str:
        """Suggest a URL for a new page."""
        slug = cluster_name.lower().replace(" ", "-")[:100]
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        return f"/{slug}"
