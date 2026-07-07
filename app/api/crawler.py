"""
API routes for the website crawler.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Project

router = APIRouter()


@router.post("/{project_id}")
async def crawl_website(
    project_id: str,
    background_tasks: BackgroundTasks,
    max_pages: int = 100,
    include_js_rendering: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Start crawling a project's own website.
    Uses Trafilatura + httpx for standard pages,
    optionally Playwright for JS-rendered pages.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.crawler import CrawlerService

    crawler = CrawlerService(db)
    background_tasks.add_task(
        crawler.crawl_site,
        project=project,
        max_pages=max_pages,
        use_js=include_js_rendering,
    )

    return {
        "status": "accepted",
        "message": f"Crawling started for {project.domain}",
        "project_id": project_id,
    }


@router.get("/{project_id}/pages")
async def list_crawled_pages(
    project_id: str,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List crawled pages for a project."""
    from app.models import Page

    result = await db.execute(
        select(Page)
        .where(Page.project_id == project_id, Page.is_own_site == True)
        .offset(skip)
        .limit(limit)
        .order_by(Page.created_at.desc())
    )
    pages = result.scalars().all()
    return {
        "pages": [
            {
                "id": p.id,
                "url": p.url,
                "title": p.title,
                "status_code": p.status_code,
                "word_count": p.word_count,
                "indexable": p.indexable,
                "last_crawled_at": str(p.last_crawled_at) if p.last_crawled_at else None,
            }
            for p in pages
        ],
        "total": len(pages),
    }
