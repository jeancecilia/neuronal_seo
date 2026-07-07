"""
API routes for embedding generation and vector search.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Project

router = APIRouter()


class EmbeddingGenerateRequest(BaseModel):
    object_type: str  # keyword, page, chunk
    object_ids: Optional[List[str]] = None  # if None, generate for all un-embedded


class SimilaritySearchRequest(BaseModel):
    text: str
    object_type: str = "page"
    limit: int = 10
    min_similarity: float = 0.5


@router.post("/{project_id}/generate")
async def generate_embeddings(
    project_id: str,
    background_tasks: BackgroundTasks,
    object_type: str = "all",
    db: AsyncSession = Depends(get_db),
):
    """
    Generate embeddings for project data (keywords, pages, chunks).
    Uses OpenAI embeddings or local sentence-transformers based on config.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.embedding_service import EmbeddingService

    service = EmbeddingService(db)
    background_tasks.add_task(
        service.generate_project_embeddings,
        project=project,
        object_type=object_type,
    )

    return {
        "status": "accepted",
        "message": f"Embedding generation started for {project.domain}",
        "project_id": project_id,
        "object_type": object_type,
    }


@router.post("/{project_id}/search")
async def similarity_search(
    project_id: str,
    request: SimilaritySearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Search for semantically similar content using vector similarity.
    Finds pages, keywords, or chunks close to the query text.
    """
    from app.services.embedding_service import EmbeddingService

    service = EmbeddingService(db)
    results = await service.similarity_search(
        project_id=project_id,
        query_text=request.text,
        object_type=request.object_type,
        limit=request.limit,
        min_similarity=request.min_similarity,
    )

    return {"query": request.text, "results": results, "total": len(results)}


@router.get("/{project_id}/stats")
async def embedding_stats(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get embedding statistics for a project."""
    from app.models import Embedding
    from sqlalchemy import func

    counts = {}
    for obj_type in ["keyword", "page", "chunk"]:
        cnt = (await db.execute(
            select(func.count(Embedding.id)).where(
                Embedding.object_type == obj_type,
                Embedding.object_id.in_(
                    select(Embedding.object_id).where(
                        # Filter by project-related object IDs
                        # Simplified: count all embeddings of this type
                    )
                ),
            )
        )).scalar()
        counts[obj_type] = cnt or 0

    return {"project_id": project_id, "embedding_counts": counts}
