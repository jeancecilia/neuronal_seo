"""
Test that Alembic migrations work correctly.
Runs real alembic upgrade/downgrade to validate the migration file.
"""

import os
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_alembic_upgrade_head_creates_all_tables():
    """
    Real test: run alembic downgrade+upgrade and verify all 14 tables exist.
    Uses subprocess to avoid asyncio.run() conflict with pytest-asyncio.
    """
    # Get database URL
    db_host = os.environ.get("POSTGRES_HOST", "postgres")
    sync_url = f"postgresql+psycopg2://neuronal_seo:neuronal_seo_pass@{db_host}:5432/neuronal_seo"
    async_url = f"postgresql+asyncpg://neuronal_seo:neuronal_seo_pass@{db_host}:5432/neuronal_seo"

    # Step 1: Downgrade to clean state
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "downgrade", "base"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "SQLALCHEMY_URL": sync_url},
    )
    assert result.returncode == 0, f"Downgrade failed: {result.stderr}"

    # Step 2: Upgrade to create all tables
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "SQLALCHEMY_URL": sync_url},
    )
    assert result.returncode == 0, f"Upgrade failed: {result.stderr}"
    assert "Running upgrade" in result.stdout or result.returncode == 0, \
        "Migration should complete successfully"

    # Step 3: Verify all tables exist
    engine = create_async_engine(async_url, echo=False)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        )
        tables = [row[0] for row in result.fetchall()]
    await engine.dispose()

    expected_tables = [
        "alembic_version", "competitor_pages", "content_gaps",
        "embeddings", "gsc_performance", "internal_link_suggestions",
        "keyword_clusters", "keywords", "page_chunks", "pages",
        "projects", "reports", "seo_tasks", "serp_results",
    ]

    for table in expected_tables:
        assert table in tables, f"Table '{table}' missing after alembic upgrade head"

    # Step 4: Run again to verify idempotency (no-op on already migrated DB)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "SQLALCHEMY_URL": sync_url},
    )
    assert result.returncode == 0, "Second upgrade should be idempotent"


@pytest.mark.asyncio
async def test_migration_columns(db_session):
    """Verify key columns exist in major tables after migration."""
    from sqlalchemy import text

    # Check projects table
    result = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'projects' ORDER BY ordinal_position"
        )
    )
    columns = [row[0] for row in result.fetchall()]
    assert "domain" in columns
    assert "target_country" in columns
    assert "services" in columns

    # Check pages table has render_mode
    result = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'pages' ORDER BY ordinal_position"
        )
    )
    columns = [row[0] for row in result.fetchall()]
    assert "render_mode" in columns, "pages table must have render_mode column"
    assert "url" in columns
    assert "title" in columns
    assert "content" in columns

    # Check embeddings table
    result = await db_session.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'embeddings'"
        )
    )
    emb_columns = {row[0]: row[1] for row in result.fetchall()}
    assert "embedding" in emb_columns, "embeddings must have embedding column"


@pytest.mark.asyncio
async def test_migration_foreign_keys(db_session):
    """Verify foreign key relationships exist after migration."""
    from sqlalchemy import text

    result = await db_session.execute(
        text(
            "SELECT tc.table_name, kcu.column_name, "
            "ccu.table_name AS foreign_table_name "
            "FROM information_schema.table_constraints AS tc "
            "JOIN information_schema.key_column_usage AS kcu "
            "ON tc.constraint_name = kcu.constraint_name "
            "JOIN information_schema.constraint_column_usage AS ccu "
            "ON ccu.constraint_name = tc.constraint_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY'"
        )
    )
    fks = [(row[0], row[1], row[2]) for row in result.fetchall()]

    # pages -> projects
    assert any(
        t == "pages" and c == "project_id" and f == "projects"
        for t, c, f in fks
    ), "pages must reference projects"

    # keywords -> projects
    assert any(
        t == "keywords" and c == "project_id" and f == "projects"
        for t, c, f in fks
    ), "keywords must reference projects"
