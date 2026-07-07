"""
Embedding generation and vector similarity search service.
Supports both OpenAI embeddings and local sentence-transformers models.
"""

import hashlib
import math
from typing import List, Optional, Tuple

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Project,
    Page,
    PageChunk,
    Keyword,
    CompetitorPage,
    Embedding,
)


class EmbeddingService:
    """
    Generates text embeddings and performs vector similarity search.
    Uses OpenAI text-embedding-3-large by default, with local model fallback.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.model_name = settings.openai_embedding_model
        self.api_key = settings.openai_api_key
        self.local_model_name = settings.local_embedding_model
        self._local_model = None
        self._embedding_dim = 3072  # text-embedding-3-large default

    async def generate_project_embeddings(
        self,
        project: Project,
        object_type: str = "all",
    ) -> dict:
        """Generate embeddings for all entities in a project."""
        results = {"keywords": 0, "pages": 0, "chunks": 0, "competitor_pages": 0}

        if object_type in ("all", "keyword"):
            results["keywords"] = await self._embed_keywords(project.id)

        if object_type in ("all", "page"):
            results["pages"] = await self._embed_pages(project.id)

        if object_type in ("all", "competitor_page"):
            results["competitor_pages"] = await self._embed_competitor_pages(project.id)

        return results

    async def _embed_keywords(self, project_id: str) -> int:
        """Generate embeddings for all project keywords."""
        result = await self.db.execute(
            select(Keyword).where(Keyword.project_id == project_id)
        )
        keywords = result.scalars().all()

        count = 0
        for kw in keywords:
            text = kw.keyword
            text_hash = hashlib.sha256(text.encode()).hexdigest()

            # Check if already embedded
            existing = await self.db.execute(
                select(Embedding).where(
                    Embedding.object_type == "keyword",
                    Embedding.object_id == kw.id,
                )
            )
            if existing.scalar_one_or_none():
                continue

            embedding_vector = await self._embed_text(text)
            if embedding_vector is not None:
                emb = Embedding(
                    object_type="keyword",
                    object_id=kw.id,
                    embedding=embedding_vector.tolist(),
                    model=self.model_name,
                    text_hash=text_hash,
                )
                self.db.add(emb)
                count += 1

        await self.db.flush()
        return count

    async def _embed_pages(self, project_id: str) -> int:
        """Generate embeddings for page content chunks."""
        result = await self.db.execute(
            select(Page).where(
                Page.project_id == project_id,
                Page.is_own_site == True,
                Page.content.isnot(None),
            )
        )
        pages = result.scalars().all()

        count = 0
        for page in pages:
            if not page.content:
                continue

            # Chunk the content
            chunks = self._chunk_text(page.content, max_tokens=500)

            for i, chunk in enumerate(chunks):
                text_hash = hashlib.sha256(chunk.encode()).hexdigest()

                # Check existing
                existing = await self.db.execute(
                    select(Embedding).where(
                        Embedding.object_type == "chunk",
                        Embedding.text_hash == text_hash,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                embedding_vector = await self._embed_text(chunk)
                if embedding_vector is not None:
                    # Save chunk
                    page_chunk = PageChunk(
                        page_id=page.id,
                        chunk_index=i,
                        content=chunk,
                        chunk_type="paragraph",
                        token_count=len(chunk.split()),
                    )
                    self.db.add(page_chunk)
                    await self.db.flush()

                    emb = Embedding(
                        object_type="chunk",
                        object_id=page_chunk.id,
                        embedding=embedding_vector.tolist(),
                        model=self.model_name,
                        text_hash=text_hash,
                    )
                    self.db.add(emb)
                    count += 1

        await self.db.flush()
        return count

    async def _embed_competitor_pages(self, project_id: str) -> int:
        """Generate embeddings for competitor page content."""
        result = await self.db.execute(
            select(CompetitorPage).where(
                CompetitorPage.project_id == project_id,
                CompetitorPage.content.isnot(None),
            )
        )
        pages = result.scalars().all()

        count = 0
        for cp in pages:
            if not cp.content:
                continue

            text_to_embed = f"{cp.title or ''} {cp.content[:3000]}"
            text_hash = hashlib.sha256(text_to_embed.encode()).hexdigest()

            existing = await self.db.execute(
                select(Embedding).where(
                    Embedding.object_type == "competitor_page",
                    Embedding.object_id == cp.id,
                )
            )
            if existing.scalar_one_or_none():
                continue

            embedding_vector = await self._embed_text(text_to_embed)
            if embedding_vector is not None:
                emb = Embedding(
                    object_type="competitor_page",
                    object_id=cp.id,
                    embedding=embedding_vector.tolist(),
                    model=self.model_name,
                    text_hash=text_hash,
                )
                self.db.add(emb)
                count += 1

        await self.db.flush()
        return count

    async def _embed_text(self, text: str) -> Optional[np.ndarray]:
        """Embed a single text string. Tries OpenAI first, falls back to local model."""
        if not text or not text.strip():
            return None

        # Try OpenAI embeddings
        if self.api_key and "sk-" in self.api_key:
            try:
                import openai
                client = openai.AsyncOpenAI(api_key=self.api_key)
                response = await client.embeddings.create(
                    model=self.model_name,
                    input=text[:8000],  # truncate to fit token limit
                )
                return np.array(response.data[0].embedding, dtype=np.float32)
            except Exception:
                pass

        # Fall back to local sentence-transformer
        return await self._embed_local(text)

    async def _embed_local(self, text: str) -> Optional[np.ndarray]:
        """Use local sentence-transformers model for embeddings."""
        try:
            if self._local_model is None:
                from sentence_transformers import SentenceTransformer
                self._local_model = SentenceTransformer(self.local_model_name)
                self._embedding_dim = self._local_model.get_sentence_embedding_dimension()

            embedding = self._local_model.encode(
                text[:2000],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return embedding.astype(np.float32)
        except Exception:
            return None

    async def similarity_search(
        self,
        project_id: str,
        query_text: str,
        object_type: str = "page",
        limit: int = 10,
        min_similarity: float = 0.5,
    ) -> List[dict]:
        """
        Perform vector similarity search for a query against stored embeddings.
        Returns the most similar items with their similarity scores.
        """
        # Generate embedding for query
        query_embedding = await self._embed_text(query_text)
        if query_embedding is None:
            return []

        # Use pgvector cosine similarity (<=> is cosine distance)
        vector_str = "[" + ",".join(str(v) for v in query_embedding.tolist()) + "]"

        sql = text("""
            SELECT
                e.object_type,
                e.object_id,
                1 - (e.embedding <=> CAST(:query_vec AS vector)) AS similarity
            FROM embeddings e
            WHERE e.object_type = :obj_type
              AND 1 - (e.embedding <=> CAST(:query_vec AS vector)) >= :min_sim
            ORDER BY similarity DESC
            LIMIT :limit
        """)

        result = await self.db.execute(
            sql,
            {
                "query_vec": vector_str,
                "obj_type": object_type,
                "min_sim": min_similarity,
                "limit": limit,
            },
        )
        rows = result.fetchall()

        results = []
        for row in rows:
            obj_type, obj_id, similarity = row
            detail = await self._get_object_detail(obj_type, obj_id)
            if detail:
                results.append({
                    "object_type": obj_type,
                    "object_id": obj_id,
                    "similarity": round(float(similarity), 4),
                    **detail,
                })

        return results

    async def _get_object_detail(self, obj_type: str, obj_id: str) -> Optional[dict]:
        """Get human-readable details for an embedded object."""
        if obj_type == "keyword":
            result = await self.db.execute(select(Keyword).where(Keyword.id == obj_id))
            kw = result.scalar_one_or_none()
            if kw:
                return {"text": kw.keyword, "intent": kw.intent}

        elif obj_type == "chunk":
            result = await self.db.execute(select(PageChunk).where(PageChunk.id == obj_id))
            chunk = result.scalar_one_or_none()
            if chunk:
                return {"text": chunk.content[:200], "heading_context": chunk.heading_context}

        elif obj_type == "competitor_page":
            result = await self.db.execute(select(CompetitorPage).where(CompetitorPage.id == obj_id))
            cp = result.scalar_one_or_none()
            if cp:
                return {"text": cp.title, "url": cp.url, "domain": cp.domain}

        return None

    def _chunk_text(self, text: str, max_tokens: int = 500, overlap: int = 50) -> List[str]:
        """Split text into overlapping chunks for embedding."""
        words = text.split()
        chunks = []

        if len(words) <= max_tokens:
            return [text]

        i = 0
        while i < len(words):
            chunk = " ".join(words[i : i + max_tokens])
            chunks.append(chunk)
            i += max_tokens - overlap

        return chunks
