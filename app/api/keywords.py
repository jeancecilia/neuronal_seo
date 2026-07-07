"""
API routes for keyword management.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Project, Keyword

router = APIRouter()


class KeywordBatchCreate(BaseModel):
    keywords: List[str]
    language: str = "de"
    country: str = "DE"
    city: Optional[str] = None
    source: str = "manual"


class KeywordResponse(BaseModel):
    id: str
    keyword: str
    language: str
    country: str
    city: Optional[str]
    intent: Optional[str]
    business_value: int
    cluster_id: Optional[str]
    search_volume: Optional[int]
    model_config = {"from_attributes": True}


@router.post("/{project_id}/batch", status_code=201)
async def add_keywords(
    project_id: str,
    data: KeywordBatchCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add multiple keywords in batch."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    added = []
    for kw_text in data.keywords:
        # Skip duplicates
        existing = await db.execute(
            select(Keyword).where(
                Keyword.project_id == project_id,
                Keyword.keyword == kw_text.strip(),
            )
        )
        if existing.scalar_one_or_none():
            continue

        kw = Keyword(
            project_id=project_id,
            keyword=kw_text.strip(),
            language=data.language,
            country=data.country,
            city=data.city,
            source=data.source,
        )
        db.add(kw)
        added.append(kw_text)

    await db.flush()
    return {"added": len(added), "keywords": added}


@router.get("/{project_id}", response_model=List[KeywordResponse])
async def list_keywords(
    project_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """List keywords for a project."""
    result = await db.execute(
        select(Keyword)
        .where(Keyword.project_id == project_id)
        .offset(skip)
        .limit(limit)
        .order_by(Keyword.business_value.desc())
    )
    return result.scalars().all()


@router.post("/{project_id}/generate-seeds")
async def generate_seed_keywords(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Generate seed keywords from project context and competitor data."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.keyword_engine import KeywordSeedEngine

    engine = KeywordSeedEngine(db)
    background_tasks.add_task(engine.generate_seeds, project)

    return {
        "status": "accepted",
        "message": f"Seed keyword generation started for {project.domain}",
        "project_id": project_id,
    }


@router.delete("/{project_id}/{keyword_id}")
async def delete_keyword(
    project_id: str,
    keyword_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a keyword."""
    result = await db.execute(
        select(Keyword).where(
            Keyword.id == keyword_id,
            Keyword.project_id == project_id,
        )
    )
    kw = result.scalar_one_or_none()
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword not found")

    await db.delete(kw)
    return {"status": "deleted", "keyword_id": keyword_id}
