"""
API routes for report generation and email delivery.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Project, Report

router = APIRouter()


class EmailTestRequest(BaseModel):
    email: str


@router.post("/{project_id}/generate")
async def generate_report(
    project_id: str,
    background_tasks: BackgroundTasks,
    report_type: str = "full",
    db: AsyncSession = Depends(get_db),
):
    """Generate a complete SEO analysis report."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.report_generator import ReportGenerator

    generator = ReportGenerator(db)
    background_tasks.add_task(
        generator.generate_report,
        project=project,
        report_type=report_type,
    )

    return {
        "status": "accepted",
        "message": f"Report generation started for {project.domain}",
        "project_id": project_id,
    }


@router.get("/{project_id}/list")
async def list_reports(
    project_id: str,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List generated reports for a project."""
    result = await db.execute(
        select(Report)
        .where(Report.project_id == project_id)
        .offset(skip)
        .limit(limit)
        .order_by(Report.created_at.desc())
    )
    reports = result.scalars().all()
    return {
        "reports": [
            {
                "id": r.id,
                "title": r.title,
                "report_type": r.report_type,
                "email_sent": r.email_sent,
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in reports
        ]
    }


@router.get("/{project_id}/{report_id}")
async def get_report(
    project_id: str,
    report_id: str,
    format: str = "json",
    db: AsyncSession = Depends(get_db),
):
    """Get a specific report in JSON or download the Markdown file."""
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.project_id == project_id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if format == "markdown":
        return {"title": report.title, "content": report.content_markdown}

    if format == "download" and report.file_path:
        return FileResponse(
            path=report.file_path,
            filename=f"seo_report_{report.id}.md",
            media_type="text/markdown",
        )

    return {
        "id": report.id,
        "title": report.title,
        "report_type": report.report_type,
        "content": report.content_json,
        "email_sent": report.email_sent,
        "created_at": str(report.created_at) if report.created_at else None,
    }


@router.post("/{project_id}/send-email")
async def send_report_by_email(
    project_id: str,
    background_tasks: BackgroundTasks,
    email: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a report and send it via email immediately.
    Uses the configured SMTP settings and recipient from .env.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.scheduler import send_report_for_project

    background_tasks.add_task(
        send_report_for_project,
        project_id=project_id,
        to_email=email,
    )

    return {
        "status": "accepted",
        "message": f"Report generation and email delivery started for {project.domain}",
        "project_id": project_id,
    }


@router.post("/test-email")
async def test_email_config(request: EmailTestRequest):
    """Test SMTP configuration by sending a test email."""
    from app.services.email_sender import EmailSender

    sender = EmailSender()
    result = await sender.send_test_email(request.email)
    return result


@router.post("/schedule/weekly/start")
async def start_weekly_scheduler(
    day: str = "mon",
    hour: int = 8,
    minute: int = 0,
):
    """
    Start the weekly report scheduler.
    Generates and emails reports automatically on schedule.

    Args:
        day: Day of week (mon, tue, wed, thu, fri, sat, sun)
        hour: Hour in UTC (0-23)
        minute: Minute (0-59)
    """
    from app.services.scheduler import WeeklyReportScheduler

    sched = WeeklyReportScheduler()
    sched.start(day_of_week=day, hour=hour, minute=minute)

    return {
        "status": "started",
        "schedule": f"Every {day} at {hour:02d}:{minute:02d} UTC",
    }


@router.post("/schedule/weekly/stop")
async def stop_weekly_scheduler():
    """Stop the weekly report scheduler."""
    from app.services.scheduler import WeeklyReportScheduler

    sched = WeeklyReportScheduler()
    sched.stop()

    return {"status": "stopped"}


@router.post("/schedule/run-now")
async def run_weekly_now():
    """Manually trigger the weekly report generation for all projects now."""
    from app.services.scheduler import WeeklyReportScheduler

    sched = WeeklyReportScheduler()
    result = await sched.run_manual_now()
    return result
