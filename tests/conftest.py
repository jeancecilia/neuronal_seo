"""
Shared pytest fixtures for Neuronal SEO test suite.
Uses Docker internal hostnames (postgres, redis) when running inside containers.
All fixtures use alembic migrations, not Base.metadata.create_all.
"""

import os
import subprocess
import sys
import uuid
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# In Docker, the database is at 'postgres' hostname (Docker network)
DB_HOST = os.environ.get("POSTGRES_HOST", "postgres")
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"postgresql+asyncpg://neuronal_seo:neuronal_seo_pass@{DB_HOST}:5432/neuronal_seo",
)
SYNC_DB_URL = f"postgresql+psycopg2://neuronal_seo:neuronal_seo_pass@{DB_HOST}:5432/neuronal_seo"


def _run_alembic_upgrade() -> None:
    """Run alembic upgrade head using subprocess (avoids asyncio conflicts)."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "SQLALCHEMY_URL": SYNC_DB_URL},
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed: {result.stderr}")


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session that uses alembic migrations.
    Rolls back after each test to keep DB clean.
    """
    # Ensure tables exist via alembic (idempotent if already migrated)
    _run_alembic_upgrade()

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_app():
    """Provide a FastAPI test app with database.
    Ensures alembic migration has run before yielding app.
    """
    _run_alembic_upgrade()

    from app.main import app
    from app.core.database import get_db

    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    test_session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client for testing the API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
