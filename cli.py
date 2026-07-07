#!/usr/bin/env python
"""
Neuronal SEO CLI - Command line interface for the SEO Intelligence Pipeline.

Usage:
    python cli.py create-project --domain example.com --country DE --language de --cities "Köln,Bonn" --services "App Entwicklung"
    python cli.py run-pipeline --project-id <uuid>
    python cli.py generate-report --project-id <uuid>
    python cli.py send-report --project-id <uuid> --email recipient@example.com
    python cli.py test-email --email recipient@example.com
    python cli.py schedule-start --day mon --hour 8
"""

import asyncio
import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from app.core.config import settings
from app.core.database import async_session_factory, init_vector_extension
from app.models import Project

app = typer.Typer(help="Neuronal SEO Intelligence Pipeline CLI")
console = Console()


@app.command()
def create_project(
    domain: str = typer.Option(..., help="Target domain"),
    country: str = typer.Option("DE", help="Target country code"),
    language: str = typer.Option("de", help="Target language code"),
    cities: str = typer.Option("", help="Comma-separated target cities"),
    services: str = typer.Option("", help="Comma-separated services"),
    competitors: str = typer.Option("", help="Comma-separated competitor domains"),
):
    """Create a new SEO project."""
    async def _create():
        await init_vector_extension()
        async with async_session_factory() as db:
            project = Project(
                domain=domain,
                target_country=country,
                target_language=language,
                target_cities=[c.strip() for c in cities.split(",") if c.strip()],
                services=[s.strip() for s in services.split(",") if s.strip()],
                competitors=[c.strip() for c in competitors.split(",") if c.strip()],
            )
            db.add(project)
            await db.commit()
            console.print(f"[green]✓[/green] Created project [bold]{project.id}[/bold] for {domain}")
            return project.id

    project_id = asyncio.run(_create())
    console.print(f"Use this ID to run the pipeline: [cyan]python cli.py run-pipeline --project-id {project_id}[/cyan]")


@app.command()
def run_pipeline(
    project_id: str = typer.Option(..., help="Project UUID"),
    steps: str = typer.Option("all", help="Pipeline steps: all, crawl, serp, embeddings, analysis, report"),
):
    """Run the SEO analysis pipeline for a project."""
    async def _run():
        async with async_session_factory() as db:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                console.print(f"[red]✗[/red] Project {project_id} not found")
                return

            console.print(f"[bold]Starting pipeline for {project.domain}[/bold]")

        from app.services.pipeline import run_pipeline_for_project
        results = await run_pipeline_for_project(project_id)

        if results["status"] == "completed":
            console.print(f"\n[green]✓[/green] Pipeline completed!")
            for step_name, step_result in results["steps"].items():
                console.print(f"  • {step_name}: {step_result}")
            if "report" in results.get("steps", {}):
                console.print(f"\n[bold]Report:[/bold] {results['steps']['report'].get('file_path')}")
        else:
            console.print(f"\n[red]✗[/red] Pipeline failed: {results.get('error')}")

    asyncio.run(_run())


@app.command()
def generate_report(
    project_id: str = typer.Option(..., help="Project UUID"),
):
    """Generate a Markdown SEO report for a project."""
    async def _gen():
        async with async_session_factory() as db:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                console.print(f"[red]✗[/red] Project not found")
                return

            from app.services.report_generator import ReportGenerator
            generator = ReportGenerator(db)
            report = await generator.generate_report(project, report_type="on_demand")
            await db.commit()

            console.print(f"[green]✓[/green] Report generated!")
            console.print(f"  Report ID: {report.id}")
            console.print(f"  File: {report.file_path}")

    asyncio.run(_gen())


@app.command()
def list_projects():
    """List all projects."""
    async def _list():
        async with async_session_factory() as db:
            result = await db.execute(select(Project).order_by(Project.created_at.desc()))
            projects = result.scalars().all()

            table = Table(title="SEO Projects")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Domain", style="green")
            table.add_column("Country")
            table.add_column("Language")
            table.add_column("Services")
            table.add_column("Created")

            for p in projects:
                table.add_row(
                    p.id[:8] + "...",
                    p.domain,
                    p.target_country,
                    p.target_language,
                    ", ".join(p.services or [])[:40],
                    str(p.created_at)[:19] if p.created_at else "",
                )

            console.print(table)

    asyncio.run(_list())


@app.command()
def stats(
    project_id: str = typer.Option(..., help="Project UUID"),
):
    """Show project statistics."""
    async def _stats():
        from sqlalchemy import func, select as sa_select
        from app.models import Page, Keyword, KeywordCluster, ContentGap, SeoTask

        async with async_session_factory() as db:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                console.print(f"[red]✗[/red] Project not found")
                return

            pages = (await db.execute(
                sa_select(func.count(Page.id)).where(Page.project_id == project_id)
            )).scalar()

            keywords = (await db.execute(
                sa_select(func.count(Keyword.id)).where(Keyword.project_id == project_id)
            )).scalar()

            clusters = (await db.execute(
                sa_select(func.count(KeywordCluster.id)).where(KeywordCluster.project_id == project_id)
            )).scalar()

            gaps = (await db.execute(
                sa_select(func.count(ContentGap.id)).where(ContentGap.project_id == project_id)
            )).scalar()

            tasks = (await db.execute(
                sa_select(func.count(SeoTask.id)).where(SeoTask.project_id == project_id)
            )).scalar()

            table = Table(title=f"Stats for {project.domain}")
            table.add_column("Metric")
            table.add_column("Value", style="cyan")

            table.add_row("Pages", str(pages))
            table.add_row("Keywords", str(keywords))
            table.add_row("Clusters", str(clusters))
            table.add_row("Content Gaps", str(gaps))
            table.add_row("SEO Tasks", str(tasks))

            console.print(table)

    asyncio.run(_stats())


@app.command()
def seed_keywords(
    project_id: str = typer.Option(..., help="Project UUID"),
):
    """Generate seed keywords from project configuration."""
    async def _seed():
        async with async_session_factory() as db:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                console.print(f"[red]✗[/red] Project not found")
                return

            from app.services.keyword_engine import KeywordSeedEngine
            engine = KeywordSeedEngine(db)
            keywords = await engine.generate_seeds(project)
            await db.commit()

            console.print(f"[green]✓[/green] Generated {len(keywords)} seed keywords")
            for kw in sorted(keywords)[:20]:
                console.print(f"  • {kw}")
            if len(keywords) > 20:
                console.print(f"  ... and {len(keywords) - 20} more")

    asyncio.run(_seed())


@app.command()
def send_report(
    project_id: str = typer.Option(..., help="Project UUID"),
    email: str = typer.Option(None, help="Recipient email (uses .env default if not provided)"),
):
    """Generate and email a report for a project."""
    async def _send():
        from app.services.scheduler import send_report_for_project
        result = await send_report_for_project(project_id, to_email=email)
        if result["status"] == "completed":
            console.print(f"[green]✓[/green] Report generated: {result['report_id']}")
            email_status = result.get("email", {})
            if email_status.get("status") == "sent":
                console.print(f"[green]✓[/green] Email sent to: {email_status.get('recipient')}")
            else:
                console.print(f"[yellow]⚠[/yellow] Email: {email_status.get('message', email_status.get('status'))}")
        else:
            console.print(f"[red]✗[/red] Failed: {result.get('message')}")

    asyncio.run(_send())


@app.command()
def test_email(
    email: str = typer.Option(..., help="Email address to send test to"),
):
    """Send a test email to verify SMTP configuration."""
    async def _test():
        from app.services.email_sender import EmailSender
        sender = EmailSender()
        result = await sender.send_test_email(email)
        if result["status"] == "sent":
            console.print(f"[green]✓[/green] Test email sent to {email}")
            console.print("Check your inbox. If not received, check SMTP settings in .env")
        elif result["status"] == "disabled":
            console.print("[yellow]⚠[/yellow] Email is disabled. Set EMAIL_ENABLED=true in .env")
        elif result["status"] == "skipped":
            console.print("[yellow]⚠[/yellow] SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD in .env")
        else:
            console.print(f"[red]✗[/red] Failed: {result.get('message')}")

    asyncio.run(_test())


@app.command()
def schedule_start(
    day: str = typer.Option("mon", help="Day of week (mon, tue, wed, thu, fri, sat, sun)"),
    hour: int = typer.Option(8, help="Hour in UTC (0-23)"),
    minute: int = typer.Option(0, help="Minute (0-59)"),
):
    """Start the weekly report scheduler."""
    from app.services.scheduler import WeeklyReportScheduler
    sched = WeeklyReportScheduler()
    sched.start(day_of_week=day, hour=hour, minute=minute)
    console.print(f"[green]✓[/green] Scheduler started: every {day} at {hour:02d}:{minute:02d} UTC")
    console.print("The scheduler will run in the background. Press Ctrl+C to stop.")


@app.command()
def schedule_run_now():
    """Run weekly reports for all projects immediately."""
    async def _run():
        from app.services.scheduler import WeeklyReportScheduler
        sched = WeeklyReportScheduler()
        result = await sched.run_manual_now()
        console.print(f"[green]✓[/green] Processed {result['projects_processed']} projects")
        console.print(f"  Reports sent: {result['reports_sent']}")
        console.print(f"  Errors: {result['errors']}")
        for detail in result.get("details", []):
            status = "✓" if detail.get("email_sent") else "✗"
            console.print(f"  {status} {detail.get('project', 'unknown')}")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
