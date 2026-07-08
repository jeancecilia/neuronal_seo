"""
API routes for SEO analysis: clustering, intent, content gaps, internal links, scoring.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Project, KeywordCluster, ContentGap, InternalLinkSuggestion, SeoTask

router = APIRouter()


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------
@router.post("/{project_id}/cluster")
async def cluster_keywords(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Run semantic clustering on keywords."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.clustering import ClusteringService

    service = ClusteringService(db)
    background_tasks.add_task(service.cluster_keywords, project)

    return {"status": "accepted", "message": "Clustering started", "project_id": project_id}


@router.get("/{project_id}/clusters")
async def list_clusters(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get keyword clusters for a project."""
    result = await db.execute(
        select(KeywordCluster)
        .where(KeywordCluster.project_id == project_id)
        .order_by(KeywordCluster.cluster_size.desc())
    )
    clusters = result.scalars().all()
    return {
        "clusters": [
            {
                "id": c.id,
                "name": c.name,
                "primary_keyword": c.primary_keyword,
                "intent": c.intent,
                "action": c.action,
                "cluster_size": c.cluster_size,
                "keywords": c.keywords_list,
            }
            for c in clusters
        ]
    }


# ---------------------------------------------------------------------------
# Intent Classification
# ---------------------------------------------------------------------------
@router.post("/{project_id}/classify-intent")
async def classify_intent(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Classify search intent for all keywords and clusters."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.intent_classifier import IntentClassifier

    classifier = IntentClassifier(db)
    background_tasks.add_task(classifier.classify_all, project)

    return {"status": "accepted", "message": "Intent classification started", "project_id": project_id}


# ---------------------------------------------------------------------------
# Page Mapping
# ---------------------------------------------------------------------------
@router.post("/{project_id}/map-pages")
async def map_clusters_to_pages(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Map keyword clusters to target pages with actions."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.page_mapper import PageMapper

    mapper = PageMapper(db)
    background_tasks.add_task(mapper.map_clusters, project)

    return {"status": "accepted", "message": "Page mapping started", "project_id": project_id}


# ---------------------------------------------------------------------------
# Content Gaps
# ---------------------------------------------------------------------------
@router.post("/{project_id}/detect-gaps")
async def detect_content_gaps(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Detect content gaps by comparing your pages against competitors."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.content_gap import ContentGapDetector

    detector = ContentGapDetector(db)
    background_tasks.add_task(detector.detect_gaps, project)

    return {"status": "accepted", "message": "Content gap detection started", "project_id": project_id}


@router.get("/{project_id}/gaps")
async def list_content_gaps(
    project_id: str,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List content gaps for a project."""
    query = select(ContentGap).where(ContentGap.project_id == project_id)
    if severity:
        query = query.where(ContentGap.severity == severity)
    if status:
        query = query.where(ContentGap.status == status)

    result = await db.execute(query.order_by(ContentGap.severity.desc()))
    gaps = result.scalars().all()
    return {
        "gaps": [
            {
                "id": g.id,
                "gap_type": g.gap_type,
                "description": g.description,
                "severity": g.severity,
                "suggested_fix": g.suggested_fix,
                "status": g.status,
            }
            for g in gaps
        ]
    }


# ---------------------------------------------------------------------------
# Internal Linking
# ---------------------------------------------------------------------------
@router.post("/{project_id}/suggest-links")
async def generate_link_suggestions(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Generate internal link suggestions using semantic similarity."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.internal_linking import InternalLinkingEngine

    engine = InternalLinkingEngine(db)
    background_tasks.add_task(engine.generate_suggestions, project)

    return {"status": "accepted", "message": "Link suggestions generation started", "project_id": project_id}


@router.get("/{project_id}/link-suggestions")
async def list_link_suggestions(
    project_id: str,
    status: Optional[str] = "suggested",
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List internal link suggestions."""
    query = select(InternalLinkSuggestion).where(
        InternalLinkSuggestion.project_id == project_id
    )
    if status:
        query = query.where(InternalLinkSuggestion.status == status)

    result = await db.execute(
        query.order_by(InternalLinkSuggestion.relevance_score.desc()).limit(limit)
    )
    suggestions = result.scalars().all()
    return {
        "suggestions": [
            {
                "id": s.id,
                "source_url": s.source_url,
                "target_url": s.target_url,
                "suggested_anchor": s.suggested_anchor,
                "relevance_score": s.relevance_score,
                "reason": s.reason,
            }
            for s in suggestions
        ]
    }


# ---------------------------------------------------------------------------
# Opportunity Scoring
# ---------------------------------------------------------------------------
@router.post("/{project_id}/score-opportunities")
async def score_opportunities(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Generate and score SEO opportunities."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.opportunity_scorer import OpportunityScorer

    scorer = OpportunityScorer(db)
    background_tasks.add_task(scorer.score_all, project)

    return {"status": "accepted", "message": "Opportunity scoring started", "project_id": project_id}


@router.get("/{project_id}/tasks")
async def list_seo_tasks(
    project_id: str,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List SEO tasks for a project."""
    query = select(SeoTask).where(SeoTask.project_id == project_id)
    if priority:
        query = query.where(SeoTask.priority == priority)
    if status:
        query = query.where(SeoTask.status == status)
    if category:
        query = query.where(SeoTask.category == category)

    result = await db.execute(
        query.order_by(SeoTask.priority_score.desc()).limit(limit)
    )
    tasks = result.scalars().all()
    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "reason": t.reason,
                "category": t.category,
                "priority": t.priority,
                "priority_score": t.priority_score,
                "status": t.status,
                "checklist": t.checklist,
                "expected_impact": t.expected_impact,
            }
            for t in tasks
        ]
    }
