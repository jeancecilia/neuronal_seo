"""
Test report generation service.
"""

import os
import pytest
import tempfile

from app.models import Project, Page, Keyword, KeywordCluster, ContentGap, SeoTask
from app.core.config import settings


@pytest.mark.asyncio
async def test_report_generation_creates_file(db_session):
    """Test that report generation creates a Markdown file."""
    from app.services.report_generator import ReportGenerator

    project = Project(
        domain="report-test.com",
        target_country="DE",
        target_language="de",
        target_cities=["Köln"],
        services=["App Entwicklung"],
        competitors=["competitor.de"],
    )
    db_session.add(project)
    await db_session.flush()

    # Add some pages
    page = Page(
        project_id=project.id,
        url="https://report-test.com/",
        title="Home Page",
        h1="Welcome",
        content="Some content for the home page. " * 20,
        word_count=100,
        indexable=True,
        is_own_site=True,
    )
    db_session.add(page)
    await db_session.flush()

    # Add keywords
    kw = Keyword(
        project_id=project.id,
        keyword="app entwicklung köln",
        language="de",
        country="DE",
        city="Köln",
        intent="local_transactional",
        business_value=8,
    )
    db_session.add(kw)
    await db_session.flush()

    # Add a task
    task = SeoTask(
        project_id=project.id,
        title="Test Task",
        description="A test SEO task",
        category="content",
        priority="high",
        priority_score=75.0,
    )
    db_session.add(task)
    await db_session.flush()

    # Generate report
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.report_output_dir = tmpdir
        generator = ReportGenerator(db_session)
        report = await generator.generate_report(project, report_type="test")

        assert report.id is not None
        assert report.file_path is not None
        assert os.path.exists(report.file_path)

        # Verify content
        with open(report.file_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "# SEO Analysis Report" in content
        assert "report-test.com" in content
        assert "Executive Summary" in content
        assert "Test Task" in content


@pytest.mark.asyncio
async def test_report_contains_clusters(db_session):
    """Test that report includes keyword cluster information."""
    from app.services.report_generator import ReportGenerator

    project = Project(
        domain="cluster-report.com",
        target_country="DE",
        target_language="de",
    )
    db_session.add(project)
    await db_session.flush()

    # Add a cluster
    cluster = KeywordCluster(
        project_id=project.id,
        name="App Entwicklung Köln",
        primary_keyword="app entwicklung köln",
        intent="local_transactional",
        action="create_new",
        cluster_size=5,
        keywords_list=["app entwicklung köln", "app agentur köln", "app programmierer köln"],
    )
    db_session.add(cluster)
    await db_session.flush()

    with tempfile.TemporaryDirectory() as tmpdir:
        settings.report_output_dir = tmpdir
        generator = ReportGenerator(db_session)
        report = await generator.generate_report(project, report_type="test")

        with open(report.file_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "App Entwicklung Köln" in content
        assert "app entwicklung köln" in content
        assert "create_new" in content


@pytest.mark.asyncio
async def test_report_handles_empty_project(db_session):
    """Test that report generation works for empty projects."""
    from app.services.report_generator import ReportGenerator

    project = Project(
        domain="empty-report.com",
        target_country="DE",
        target_language="de",
    )
    db_session.add(project)
    await db_session.flush()

    with tempfile.TemporaryDirectory() as tmpdir:
        settings.report_output_dir = tmpdir
        generator = ReportGenerator(db_session)
        report = await generator.generate_report(project, report_type="test")

        assert report.id is not None
        assert os.path.exists(report.file_path)

        with open(report.file_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "empty-report.com" in content
        assert "0" in content  # All counts should be zero
