"""
Weekly report scheduler using APScheduler.
Automatically generates and emails SEO reports for all projects on a schedule.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models import Project, Report

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


class WeeklyReportScheduler:
    """
    Schedules and executes weekly SEO report generation and delivery.
    Uses APScheduler for cron-based scheduling.
    """

    def __init__(self):
        self.scheduler = scheduler
        self.is_running = False

    def start(self, day_of_week: str = "mon", hour: int = 8, minute: int = 0):
        """
        Start the weekly report scheduler.

        Args:
            day_of_week: Day to run (mon, tue, wed, thu, fri, sat, sun)
            hour: Hour to run (0-23)
            minute: Minute to run (0-59)
        """
        if self.is_running:
            logger.warning("Scheduler is already running")
            return

        trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)

        self.scheduler.add_job(
            self.run_weekly_reports,
            trigger=trigger,
            id="weekly_seo_report",
            name="Weekly SEO Report Generation",
            replace_existing=True,
        )

        self.scheduler.start()
        self.is_running = True
        logger.info(
            f"Weekly report scheduler started: every {day_of_week} at {hour:02d}:{minute:02d}"
        )

    def stop(self):
        """Stop the scheduler."""
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("Scheduler stopped")

    async def run_weekly_reports(self) -> Dict:
        """
        Generate and email weekly reports for all projects.
        This is the main scheduled job.
        """
        logger.info("Starting weekly report generation for all projects...")
        results = {
            "started_at": datetime.utcnow().isoformat(),
            "projects_processed": 0,
            "reports_sent": 0,
            "errors": 0,
            "details": [],
        }

        async with async_session_factory() as db:
            try:
                # Get all projects
                result = await db.execute(select(Project))
                projects = result.scalars().all()

                if not projects:
                    logger.info("No projects found for weekly report")
                    return results

                results["projects_processed"] = len(projects)

                for project in projects:
                    try:
                        project_result = await self._process_project_weekly(project, db)
                        results["details"].append(project_result)

                        if project_result.get("email_sent"):
                            results["reports_sent"] += 1
                        if project_result.get("error"):
                            results["errors"] += 1

                    except Exception as e:
                        logger.error(f"Failed to process project {project.domain}: {e}")
                        results["details"].append({
                            "project": project.domain,
                            "error": str(e),
                        })
                        results["errors"] += 1

                await db.commit()

            except Exception as e:
                logger.error(f"Weekly report generation failed: {e}")
                await db.rollback()

        results["completed_at"] = datetime.utcnow().isoformat()
        logger.info(f"Weekly reports: {results['reports_sent']} sent, {results['errors']} errors")
        return results

    async def _process_project_weekly(
        self, project: Project, db
    ) -> Dict:
        """Process a single project for weekly reporting."""
        result = {"project": project.domain, "project_id": project.id}

        # Step 1: Run the full pipeline
        try:
            from app.services.pipeline import run_pipeline_for_project
            pipeline_result = await run_pipeline_for_project(project.id)
            result["pipeline_status"] = pipeline_result.get("status")
        except Exception as e:
            result["pipeline_error"] = str(e)
            result["pipeline_status"] = "failed"

        # Step 2: Get the latest report
        report_result = await db.execute(
            select(Report)
            .where(Report.project_id == project.id)
            .order_by(Report.created_at.desc())
            .limit(1)
        )
        report = report_result.scalar_one_or_none()

        if not report or not report.content_markdown:
            result["error"] = "No report content available"
            return result

        # Step 3: Send email
        if settings.email_enabled and settings.report_email_to:
            try:
                from app.services.email_sender import EmailSender
                sender = EmailSender()

                email_result = await sender.send_weekly_report(
                    to_email=settings.report_email_to,
                    markdown_content=report.content_markdown,
                    domain=project.domain,
                )

                result["email_sent"] = email_result.get("status") == "sent"
                result["email_status"] = email_result.get("status")

                # Update report record
                report.email_sent = email_result.get("status") == "sent"

            except Exception as e:
                result["email_error"] = str(e)
                result["email_sent"] = False
        else:
            result["email_sent"] = False
            result["email_status"] = "disabled_or_unconfigured"

        return result

    async def run_manual_now(self) -> Dict:
        """Manually trigger weekly report generation immediately."""
        logger.info("Manual weekly report run triggered")
        return await self.run_weekly_reports()


# ---------------------------------------------------------------------------
# Convenience functions for direct use
# ---------------------------------------------------------------------------
async def send_report_for_project(project_id: str, to_email: str = None) -> Dict:
    """
    Generate and send a report for a specific project.
    Useful for on-demand report delivery.
    """
    async with async_session_factory() as db:
        from app.services.report_generator import ReportGenerator

        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return {"status": "error", "message": "Project not found"}

        # Generate report
        generator = ReportGenerator(db)
        report = await generator.generate_report(project, report_type="on_demand")
        await db.commit()

        # Send email if configured
        email_result = {"status": "skipped"}
        if settings.email_enabled and (to_email or settings.report_email_to):
            from app.services.email_sender import EmailSender
            sender = EmailSender()
            recipient = to_email or settings.report_email_to

            email_result = await sender.send_report(
                to_email=recipient,
                subject=f"SEO Report — {project.domain} — {datetime.utcnow().strftime('%Y-%m-%d')}",
                markdown_content=report.content_markdown,
                domain=project.domain,
                report_type="on_demand",
            )

            if email_result.get("status") == "sent":
                report.email_sent = True
                await db.commit()

        return {
            "status": "completed",
            "report_id": report.id,
            "file_path": report.file_path,
            "email": email_result,
        }
