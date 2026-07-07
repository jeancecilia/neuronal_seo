"""
API routes for project management.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Project

router = APIRouter()

from pydantic import BaseModel
from typing import List as ListType


class ProjectCreate(BaseModel):
    domain: str
    target_country: str = "DE"
    target_language: str = "de"
    target_cities: ListType[str] = []
    services: ListType[str] = []
    business_value_per_service: Optional[dict] = None
    competitors: ListType[str] = []
    brand_terms: ListType[str] = []
    forbidden_terms: ListType[str] = []
    preferred_content_style: Optional[str] = None
    extra_context: Optional[dict] = None


class ProjectUpdate(BaseModel):
    target_country: Optional[str] = None
    target_language: Optional[str] = None
    target_cities: Optional[ListType[str]] = None
    services: Optional[ListType[str]] = None
    business_value_per_service: Optional[dict] = None
    competitors: Optional[ListType[str]] = None
    brand_terms: Optional[ListType[str]] = None
    forbidden_terms: Optional[ListType[str]] = None
    preferred_content_style: Optional[str] = None
    extra_context: Optional[dict] = None


from datetime import datetime

class ProjectResponse(BaseModel):
    id: str
    domain: str
    target_country: str
    target_language: str
    target_cities: Optional[list] = None
    services: Optional[list] = None
    competitors: Optional[list] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all projects."""
    result = await db.execute(
        select(Project).offset(skip).limit(limit).order_by(Project.created_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(project_data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """Create a new SEO project."""
    # Check if domain already exists
    existing = await db.execute(
        select(Project).where(Project.domain == project_data.domain)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Project for this domain already exists")

    project = Project(
        domain=project_data.domain,
        target_country=project_data.target_country,
        target_language=project_data.target_language,
        target_cities=project_data.target_cities,
        services=project_data.services,
        business_value_per_service=project_data.business_value_per_service,
        competitors=project_data.competitors,
        brand_terms=project_data.brand_terms,
        forbidden_terms=project_data.forbidden_terms,
        preferred_content_style=project_data.preferred_content_style,
        extra_context=project_data.extra_context,
    )
    db.add(project)
    await db.flush()
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    project_data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for field, value in project_data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    await db.flush()
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a project and all associated data."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.delete(project)
    return {"status": "deleted", "project_id": project_id}


@router.get("/{project_id}/stats")
async def get_project_stats(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get statistics for a project."""
    from app.models import Page, Keyword, SeoTask, ContentGap

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    pages_count = (await db.execute(
        select(func.count(Page.id)).where(Page.project_id == project_id)
    )).scalar()

    keywords_count = (await db.execute(
        select(func.count(Keyword.id)).where(Keyword.project_id == project_id)
    )).scalar()

    tasks_count = (await db.execute(
        select(func.count(SeoTask.id)).where(SeoTask.project_id == project_id)
    )).scalar()

    gaps_count = (await db.execute(
        select(func.count(ContentGap.id)).where(ContentGap.project_id == project_id)
    )).scalar()

    return {
        "total_pages": pages_count,
        "total_keywords": keywords_count,
        "total_tasks": tasks_count,
        "total_content_gaps": gaps_count,
    }
