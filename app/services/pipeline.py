"""
Full SEO pipeline orchestrator - Competitor-first, SERP-optional approach.

Revised flow:
1. Generate seed keywords from project context
2. Crawl own website
3. Extract own sitemap
4. Crawl competitors via sitemap-first discovery
5. Classify all pages (own + competitor)
6. Extract entities from all pages
7. Build topic maps for gap analysis
8. Generate embeddings
9. Cluster keywords semantically
10. Classify search intent
11. Map clusters to pages
12. Detect content gaps against competitor topic maps
13. Generate internal link suggestions
14. Score SEO opportunities
15. Generate report

Optional steps (not blocking):
- Light SERP sampling for validation
- Bing Webmaster Tools keyword data
- Search Console feedback (future)
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models import Project

logger = logging.getLogger(__name__)


async def run_pipeline_for_project(project_id: str) -> dict:
    """Run the complete SEO analysis pipeline for a project."""
    pipeline = Pipeline()
    return await pipeline.run(project_id)


class Pipeline:
    """Orchestrates the full SEO intelligence pipeline."""

    async def run(self, project_id: str) -> dict:
        """Execute all pipeline steps in order."""
        results = {
            "project_id": project_id,
            "started_at": datetime.utcnow().isoformat(),
            "steps": {},
            "status": "running",
        }

        async with async_session_factory() as db:
            try:
                # Load project
                result = await db.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = result.scalar_one_or_none()
                if not project:
                    return {"status": "error", "message": "Project not found"}

                # ------------------------------------------------------------------
                # Step 1: Generate seed keywords
                # ------------------------------------------------------------------
                logger.info(f"Step 1: Generating seed keywords for {project.domain}")
                from app.services.keyword_engine import KeywordSeedEngine
                seed_engine = KeywordSeedEngine(db)
                seed_keywords = await seed_engine.generate_seeds(project)
                results["steps"]["seed_keywords"] = {
                    "generated": len(seed_keywords),
                }

                # ------------------------------------------------------------------
                # Step 2: Crawl own website
                # ------------------------------------------------------------------
                logger.info(f"Step 2: Crawling own site {project.domain}")
                from app.services.crawler import CrawlerService
                crawler = CrawlerService(db)
                crawl_result = await crawler.crawl_site(project)
                results["steps"]["crawl_own_site"] = crawl_result

                # ------------------------------------------------------------------
                # Step 3: Extract own sitemap
                # ------------------------------------------------------------------
                logger.info(f"Step 3: Extracting sitemap for {project.domain}")
                from app.services.sitemap_extractor import SitemapExtractor
                sitemap_extractor = SitemapExtractor()
                own_sitemap = await sitemap_extractor.extract_from_domain(
                    project.domain
                )
                results["steps"]["own_sitemap"] = {
                    "sitemaps_found": len(own_sitemap.get("sitemap_urls", [])),
                    "pages_in_sitemap": own_sitemap.get("total_pages", 0),
                }

                # ------------------------------------------------------------------
                # Step 4: Crawl competitors (sitemap-first)
                # ------------------------------------------------------------------
                logger.info(f"Step 4: Crawling competitors for {project.domain}")
                from app.services.competitor_crawler import CompetitorCrawler
                comp_crawler = CompetitorCrawler(db)
                comp_result = await comp_crawler.crawl_competitors_sitemap_first(
                    project
                )
                results["steps"]["competitor_crawl"] = comp_result

                # ------------------------------------------------------------------
                # Step 5: Classify all pages
                # ------------------------------------------------------------------
                logger.info(f"Step 5: Classifying pages for {project.domain}")
                await self._classify_own_pages(project, db)
                results["steps"]["page_classification"] = {"status": "completed"}

                # ------------------------------------------------------------------
                # Step 6: Extract entities from all pages
                # ------------------------------------------------------------------
                logger.info(f"Step 6: Extracting entities for {project.domain}")
                await self._extract_entities(project, db)
                results["steps"]["entity_extraction"] = {"status": "completed"}

                # ------------------------------------------------------------------
                # Step 7: Build competitor topic maps
                # ------------------------------------------------------------------
                logger.info(f"Step 7: Building topic maps for {project.domain}")
                topic_map = await comp_crawler._build_topic_map(project.id)
                results["steps"]["topic_maps"] = {
                    "competitor_services": topic_map.get("all_services", []),
                    "competitor_technologies": topic_map.get("all_technologies", []),
                }

                # ------------------------------------------------------------------
                # Step 8: Generate embeddings
                # ------------------------------------------------------------------
                logger.info(f"Step 8: Generating embeddings for {project.domain}")
                from app.services.embedding_service import EmbeddingService
                emb_service = EmbeddingService(db)
                emb_result = await emb_service.generate_project_embeddings(project)
                results["steps"]["embeddings"] = emb_result

                # ------------------------------------------------------------------
                # Step 8.5: Clean old analysis data (prevents duplicates on re-run)
                # ------------------------------------------------------------------
                logger.info(f"Step 8.5: Cleaning old analysis data for {project.domain}")
                cleaned = await self._clean_analysis_data(project.id, db)
                results["steps"]["cleanup"] = cleaned

                # ------------------------------------------------------------------
                # Step 9: Cluster keywords
                # ------------------------------------------------------------------
                logger.info(f"Step 9: Clustering keywords for {project.domain}")
                from app.services.clustering import ClusteringService
                cluster_service = ClusteringService(db)
                cluster_result = await cluster_service.cluster_keywords(project)
                results["steps"]["clustering"] = {
                    "clusters_created": len(cluster_result),
                }

                # ------------------------------------------------------------------
                # Step 10: Classify intent
                # ------------------------------------------------------------------
                logger.info(f"Step 10: Classifying intent for {project.domain}")
                from app.services.intent_classifier import IntentClassifier
                classifier = IntentClassifier(db)
                intent_result = await classifier.classify_all(project)
                results["steps"]["intent"] = intent_result

                # ------------------------------------------------------------------
                # Step 11: Map clusters to pages
                # ------------------------------------------------------------------
                logger.info(f"Step 11: Mapping pages for {project.domain}")
                from app.services.page_mapper import PageMapper
                mapper = PageMapper(db)
                map_result = await mapper.map_clusters(project)
                results["steps"]["page_mapping"] = {
                    "clusters_mapped": len(map_result),
                }

                # ------------------------------------------------------------------
                # Step 12: Detect content gaps
                # ------------------------------------------------------------------
                logger.info(f"Step 12: Detecting content gaps for {project.domain}")
                from app.services.content_gap import ContentGapDetector
                gap_detector = ContentGapDetector(db)
                gap_result = await gap_detector.detect_gaps(project)
                results["steps"]["content_gaps"] = {
                    "gaps_found": len(gap_result),
                }

                # ------------------------------------------------------------------
                # Step 13: Generate internal link suggestions
                # ------------------------------------------------------------------
                logger.info(f"Step 13: Generating link suggestions for {project.domain}")
                from app.services.internal_linking import InternalLinkingEngine
                link_engine = InternalLinkingEngine(db)
                link_result = await link_engine.generate_suggestions(project)
                results["steps"]["internal_links"] = {
                    "suggestions": len(link_result),
                }

                # ------------------------------------------------------------------
                # Step 14: Score opportunities
                # ------------------------------------------------------------------
                logger.info(f"Step 14: Scoring opportunities for {project.domain}")
                from app.services.opportunity_scorer import OpportunityScorer
                scorer = OpportunityScorer(db)
                task_result = await scorer.score_all(project)
                results["steps"]["opportunities"] = {
                    "tasks_created": len(task_result),
                }

                # ------------------------------------------------------------------
                # Step 15: Generate report
                # ------------------------------------------------------------------
                logger.info(f"Step 15: Generating report for {project.domain}")
                from app.services.report_generator import ReportGenerator
                report_gen = ReportGenerator(db)
                report = await report_gen.generate_report(project)
                results["steps"]["report"] = {
                    "report_id": report.id,
                    "file_path": report.file_path,
                }

                results["status"] = "completed"
                results["completed_at"] = datetime.utcnow().isoformat()

                await db.commit()

            except Exception as e:
                logger.error(f"Pipeline failed for project {project_id}: {e}")
                results["status"] = "failed"
                results["error"] = str(e)
                await db.rollback()

        return results

    async def _classify_own_pages(self, project: Project, db: AsyncSession) -> None:
        """Classify all own pages using the page classifier."""
        from app.models import Page
        from app.services.page_classifier import PageClassifier

        classifier = PageClassifier()
        result = await db.execute(
            select(Page).where(
                Page.project_id == project.id,
                Page.is_own_site == True,
            )
        )
        pages = result.scalars().all()

        for page in pages:
            all_headings = (page.h2 or []) + (page.h3 or [])
            classification = classifier.classify(
                url=page.url,
                title=page.title or "",
                headings=all_headings,
                content=page.content or "",
                word_count=page.word_count or 0,
            )
            page.page_type = classification.get("page_type", page.page_type)

        await db.flush()

    async def _clean_analysis_data(self, project_id: str, db) -> dict:
        """
        Delete old analysis results before re-running.
        Cleans clusters, gaps, link suggestions, and tasks.
        Keeps keywords, pages, embeddings, and reports.
        """
        from app.models import KeywordCluster, ContentGap, InternalLinkSuggestion, SeoTask, Keyword
        from sqlalchemy import delete, update

        # Unlink keywords from clusters
        await db.execute(
            update(Keyword)
            .where(Keyword.project_id == project_id)
            .values(cluster_id=None)
        )

        # Delete old analysis data
        counts = {}
        for model, name in [
            (ContentGap, "content_gaps"),
            (InternalLinkSuggestion, "link_suggestions"),
            (SeoTask, "seo_tasks"),
            (KeywordCluster, "keyword_clusters"),
        ]:
            result = await db.execute(
                delete(model).where(model.project_id == project_id)
            )
            counts[name] = result.rowcount

        await db.flush()
        return counts

    async def _extract_entities(self, project: Project, db: AsyncSession) -> None:
        """Extract entities from own pages for topic map building."""
        from app.models import Page
        from app.services.entity_extractor import EntityExtractor

        extractor = EntityExtractor()
        result = await db.execute(
            select(Page).where(
                Page.project_id == project.id,
                Page.is_own_site == True,
                Page.content.isnot(None),
            )
        )
        pages = result.scalars().all()

        for page in pages:
            all_headings = (page.h2 or []) + (page.h3 or [])
            entities = extractor.extract(
                content=page.content or "",
                title=page.title or "",
                headings=all_headings,
                url=page.url,
            )
            # Store entities in page metadata (could be stored in a dedicated field)
            # For now, we log the extraction
            logger.debug(f"Entities extracted for {page.url}: {len(entities.get('services', []))} services")

        await db.flush()
