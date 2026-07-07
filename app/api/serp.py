"""
API routes for SERP data collection and manual SERP seeding.
SERP API fetching is OPTIONAL - the system works without it.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Project

router = APIRouter()


@router.post("/{project_id}/fetch")
async def fetch_serps(
    project_id: str,
    background_tasks: BackgroundTasks,
    max_keywords: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch SERP results for all keywords in a project.
    Uses DataForSEO or SerpAPI depending on configuration.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.serp_fetcher import SerpFetcher

    fetcher = SerpFetcher(db)
    background_tasks.add_task(
        fetcher.fetch_all_serps,
        project=project,
        max_keywords=max_keywords,
    )

    return {
        "status": "accepted",
        "message": f"SERP fetching started for {project.domain}",
        "project_id": project_id,
    }


@router.get("/{project_id}/results")
async def list_serp_results(
    project_id: str,
    keyword: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List SERP results for a project, optionally filtered by keyword."""
    from app.models import SerpResult

    query = select(SerpResult).where(SerpResult.project_id == project_id)
    if keyword:
        query = query.where(SerpResult.keyword.ilike(f"%{keyword}%"))

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(SerpResult.position)
    )
    results = result.scalars().all()

    return {
        "results": [
            {
                "id": r.id,
                "keyword": r.keyword,
                "position": r.position,
                "url": r.url,
                "title": r.title,
                "domain": r.domain,
                "fetched_at": str(r.fetched_at) if r.fetched_at else None,
            }
            for r in results
        ],
        "total": len(results),
    }


class ManualSerpSeedRequest(BaseModel):
    keyword: str
    urls: List[str]


@router.post("/{project_id}/seed-manual")
async def manual_serp_seeding(
    project_id: str,
    data: ManualSerpSeedRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Manual SERP seeding: provide top 5-10 URLs for a keyword manually.
    These URLs will be crawled as competitor pages.
    This replaces automated Google SERP scraping.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.serp_fetcher import SerpFetcher

    # Save the manual SERP result
    fetcher = SerpFetcher(db)
    for i, url in enumerate(data.urls):
        from app.models import SerpResult
        from urllib.parse import urlparse

        domain = urlparse(url).netloc.replace("www.", "")

        sr = SerpResult(
            project_id=project_id,
            keyword=data.keyword,
            position=i + 1,
            url=url,
            domain=domain,
            country=project.target_country,
            language=project.target_language,
        )
        db.add(sr)

    await db.flush()

    # Crawl the seeded URLs
    from app.services.competitor_crawler import CompetitorCrawler
    crawler = CompetitorCrawler(db)
    background_tasks.add_task(
        crawler.crawl_manual_urls,
        project=project,
        urls=data.urls,
    )

    return {
        "status": "accepted",
        "message": f"Manual SERP seeded for '{data.keyword}' with {len(data.urls)} URLs. Crawling started.",
        "project_id": project_id,
        "keyword": data.keyword,
    }


@router.post("/{project_id}/crawl-competitors")
async def crawl_competitor_pages(
    project_id: str,
    background_tasks: BackgroundTasks,
    max_competitors_per_keyword: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """
    Crawl competitor pages found in SERP results.
    Extracts content, headings, FAQs, trust signals, etc.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.competitor_crawler import CompetitorCrawler

    crawler = CompetitorCrawler(db)
    background_tasks.add_task(
        crawler.crawl_competitors,
        project=project,
        max_per_keyword=max_competitors_per_keyword,
    )

    return {
        "status": "accepted",
        "message": f"Competitor crawling started for {project.domain}",
        "project_id": project_id,
    }
