"""
Background task workers using Redis Queue (RQ).

Tasks:
- crawl_website: Crawl own website
- fetch_serps: Fetch SERP data for keywords
- crawl_competitors: Crawl competitor pages
- generate_embeddings: Create embedding vectors
- run_full_pipeline: Execute complete analysis pipeline
- generate_report: Create SEO report
"""

import logging
from redis import Redis
from rq import Queue

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis connection for RQ
redis_conn = Redis.from_url(settings.redis_url)
task_queue = Queue("neuronal_seo_tasks", connection=redis_conn)


def enqueue_crawl(project_id: str) -> str:
    """Enqueue website crawl task."""
    from app.services.crawler import CrawlerService
    job = task_queue.enqueue(
        "app.workers.tasks.crawl_task",
        project_id,
        job_timeout="30m",
    )
    return job.id


def enqueue_full_pipeline(project_id: str) -> str:
    """Enqueue full pipeline execution."""
    job = task_queue.enqueue(
        "app.workers.tasks.pipeline_task",
        project_id,
        job_timeout="2h",
    )
    return job.id


def enqueue_report(project_id: str) -> str:
    """Enqueue report generation."""
    job = task_queue.enqueue(
        "app.workers.tasks.report_task",
        project_id,
        job_timeout="15m",
    )
    return job.id
