"""
RQ worker tasks for background processing.
These functions are enqueued and executed by RQ workers.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def crawl_task(project_id: str) -> dict:
    """Background task: crawl a website."""
    return _run_async(_crawl_website, project_id)


def serp_task(project_id: str) -> dict:
    """Background task: fetch SERPs."""
    return _run_async(_fetch_serps, project_id)


def pipeline_task(project_id: str) -> dict:
    """Background task: run full pipeline."""
    return _run_async(_run_pipeline, project_id)


def report_task(project_id: str) -> dict:
    """Background task: generate report."""
    return _run_async(_generate_report, project_id)


def _run_async(coro_func, *args) -> dict:
    """Helper to run async functions in sync RQ workers."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_func(*args))
    finally:
        loop.close()


async def _crawl_website(project_id: str) -> dict:
    """Async implementation of crawl task."""
    from app.core.database import async_session_factory
    from app.models import Project
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return {"status": "error", "message": "Project not found"}

        from app.services.crawler import CrawlerService
        crawler = CrawlerService(db)
        result = await crawler.crawl_site(project)
        await db.commit()
        return result


async def _fetch_serps(project_id: str) -> dict:
    """Async implementation of SERP fetch task."""
    from app.core.database import async_session_factory
    from app.models import Project
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return {"status": "error", "message": "Project not found"}

        from app.services.serp_fetcher import SerpFetcher
        fetcher = SerpFetcher(db)
        result = await fetcher.fetch_all_serps(project)
        await db.commit()
        return result


async def _run_pipeline(project_id: str) -> dict:
    """Async implementation of full pipeline task."""
    from app.services.pipeline import run_pipeline_for_project
    return await run_pipeline_for_project(project_id)


async def _generate_report(project_id: str) -> dict:
    """Async implementation of report generation task."""
    from app.core.database import async_session_factory
    from app.models import Project
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return {"status": "error", "message": "Project not found"}

        from app.services.report_generator import ReportGenerator
        generator = ReportGenerator(db)
        report = await generator.generate_report(project)
        await db.commit()
        return {"status": "completed", "report_id": report.id, "file_path": report.file_path}
