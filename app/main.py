"""
Neuronal SEO - FastAPI Application
Main entry point for the SEO Intelligence Pipeline API.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db, init_vector_extension, close_db
from app.api import projects, crawler, keywords, serp, embeddings, analysis, reports


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    await init_vector_extension()

    # Start weekly scheduler if enabled
    if settings.email_enabled and os.environ.get("ENABLE_SCHEDULER", "").lower() == "true":
        from app.services.scheduler import WeeklyReportScheduler
        scheduler = WeeklyReportScheduler()
        scheduler.start(
            day_of_week=os.environ.get("SCHEDULE_DAY", "mon"),
            hour=int(os.environ.get("SCHEDULE_HOUR", "8")),
            minute=int(os.environ.get("SCHEDULE_MINUTE", "0")),
        )

    yield

    # Shutdown
    from app.services.scheduler import scheduler as aps_scheduler
    if aps_scheduler.running:
        aps_scheduler.shutdown(wait=False)
    await close_db()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Neuronal SEO",
    description="Automated SEO Intelligence Pipeline with semantic clustering, content gap analysis, and task generation.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(projects.router, prefix="/api/v1/projects", tags=["Projects"])
app.include_router(crawler.router, prefix="/api/v1/crawler", tags=["Crawler"])
app.include_router(keywords.router, prefix="/api/v1/keywords", tags=["Keywords"])
app.include_router(serp.router, prefix="/api/v1/serp", tags=["SERP (Optional)"])
app.include_router(embeddings.router, prefix="/api/v1/embeddings", tags=["Embeddings"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])


# ---------------------------------------------------------------------------
# Health & root endpoints
# ---------------------------------------------------------------------------
@app.get("/")
async def dashboard():
    """Serve the built-in dashboard."""
    dashboard_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    if os.path.exists(dashboard_path):
        return HTMLResponse(content=open(dashboard_path, encoding="utf-8").read())
    return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)


@app.get("/api")
async def root():
    """Root health check."""
    return {
        "service": "Neuronal SEO API",
        "version": "0.1.0",
        "status": "healthy",
        "dashboard": "/",
    }


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Detailed health check with DB connectivity."""
    db_ok = False
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "environment": settings.environment,
    }


# ---------------------------------------------------------------------------
# Full Pipeline endpoint
# ---------------------------------------------------------------------------
@app.post("/api/v1/pipeline/run/{project_id}")
async def run_full_pipeline(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger the full SEO analysis pipeline for a project.

    Competitor-first, SERP-optional approach:
    1. Generate seed keywords from project context
    2. Crawl own website
    3. Extract own sitemap
    4. Crawl competitors via sitemap-first discovery
    5. Classify pages & extract entities
    6. Build topic maps
    7. Generate embeddings
    8. Cluster keywords semantically
    9. Classify search intent
    10. Map clusters to pages
    11. Detect content gaps against competitors
    12. Generate internal link suggestions
    13. Score SEO opportunities
    14. Generate report
    """
    from app.services.pipeline import run_pipeline_for_project

    background_tasks.add_task(run_pipeline_for_project, project_id)
    return {
        "status": "accepted",
        "message": f"Pipeline started for project {project_id}. Check /api/v1/reports for results.",
        "project_id": project_id,
    }


# ---------------------------------------------------------------------------
# Additional utility endpoints
# ---------------------------------------------------------------------------
@app.post("/api/v1/sitemaps/extract/{domain}")
async def extract_sitemap(domain: str):
    """Extract and return sitemap data for any domain."""
    from app.services.sitemap_extractor import SitemapExtractor
    extractor = SitemapExtractor()
    return await extractor.extract_from_domain(domain)


@app.post("/api/v1/entities/extract")
async def extract_entities(text: str = "", url: str = "", title: str = ""):
    """Extract entities from text content."""
    from app.services.entity_extractor import EntityExtractor
    extractor = EntityExtractor()
    return extractor.extract(content=text, title=title, url=url)


@app.get("/api/v1/bing/keyword-ideas")
async def bing_keyword_ideas(query: str, country: str = "DE", language: str = "de"):
    """Get keyword ideas from Bing Webmaster Tools (free)."""
    from app.services.bing_webmaster import BingWebmasterTools
    bing = BingWebmasterTools()
    return await bing.get_keyword_ideas(query, country, language)
