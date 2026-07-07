"""
Internal linking engine using semantic similarity to find
relevant connections between pages.
"""

from typing import List, Dict

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Project,
    Page,
    Embedding,
    InternalLinkSuggestion,
)


class InternalLinkingEngine:
    """
    Generates internal link suggestions using vector similarity
    between page embeddings.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_suggestions(self, project: Project) -> List[Dict]:
        """Generate internal link suggestions for all project pages."""
        # Get all own pages
        result = await self.db.execute(
            select(Page).where(
                Page.project_id == project.id,
                Page.is_own_site == True,
                Page.indexable == True,
            )
        )
        pages = result.scalars().all()

        if len(pages) < 2:
            return []

        suggestions = []
        existing_pairs = await self._get_existing_suggestions(project.id)
        existing_set = {(s.source_url, s.target_url) for s in existing_pairs}

        for source_page in pages:
            # Find semantically similar pages
            similar = await self._find_similar_pages(source_page, pages, project.id)

            for target_page, score, reason in similar:
                pair = (source_page.url, target_page.url)

                # Skip self-links and existing suggestions
                if source_page.url == target_page.url:
                    continue
                if pair in existing_set:
                    continue

                # Generate natural anchor text
                anchor = self._generate_anchor(source_page, target_page)

                suggestion = InternalLinkSuggestion(
                    project_id=project.id,
                    source_page_id=source_page.id,
                    source_url=source_page.url,
                    target_page_id=target_page.id,
                    target_url=target_page.url,
                    suggested_anchor=anchor,
                    relevance_score=score,
                    reason=reason,
                )
                self.db.add(suggestion)
                suggestions.append({
                    "source_url": source_page.url,
                    "target_url": target_page.url,
                    "anchor": anchor,
                    "score": score,
                    "reason": reason,
                })
                existing_set.add(pair)

        await self.db.flush()
        return suggestions

    async def _find_similar_pages(
        self,
        source: Page,
        all_pages: List[Page],
        project_id: str,
        max_results: int = 5,
    ) -> List[tuple]:
        """Find pages similar to the source page using embeddings."""
        similar = []

        # Try vector similarity first
        try:
            # Get source page embedding from first chunk
            result = await self.db.execute(
                select(Embedding).where(
                    Embedding.object_type == "chunk",
                    Embedding.object_id.in_(
                        select(Embedding.object_id).where(
                            Embedding.object_type == "chunk"
                        ).limit(1)
                    ),
                )
            )
            source_emb = result.scalar_one_or_none()

            if source_emb and source_emb.embedding is not None:
                # Find similar embeddings
                sql = text("""
                    SELECT e.object_id, 1 - (e.embedding <=> :vec::vector) AS similarity
                    FROM embeddings e
                    WHERE e.object_type = 'chunk'
                      AND e.id != :source_id
                    ORDER BY similarity DESC
                    LIMIT :limit
                """)

                vector_str = "[" + ",".join(str(v) for v in source_emb.embedding) + "]"
                result = await self.db.execute(
                    sql,
                    {"vec": vector_str, "source_id": source_emb.id, "limit": max_results * 2},
                )
                rows = result.fetchall()

                for row in rows:
                    chunk_id, similarity = row
                    # Find page for this chunk
                    from app.models import PageChunk
                    chunk_result = await self.db.execute(
                        select(PageChunk).where(PageChunk.id == chunk_id)
                    )
                    chunk = chunk_result.scalar_one_or_none()
                    if chunk:
                        target_page = next(
                            (p for p in all_pages if p.id == chunk.page_id), None
                        )
                        if target_page and target_page.url != source.url:
                            similar.append((
                                target_page,
                                round(float(similarity), 4),
                                f"Semantic similarity score: {round(float(similarity), 2)}",
                            ))

                if similar:
                    return similar[:max_results]

        except Exception:
            pass

        # Fallback: keyword overlap similarity
        for target in all_pages:
            if target.url == source.url:
                continue
            if len(similar) >= max_results:
                break

            score = self._text_overlap_score(source, target)
            if score > 0.15:
                similar.append((
                    target,
                    round(score, 4),
                    f"Topic overlap score: {round(score, 2)}",
                ))

        # Sort by score descending
        similar.sort(key=lambda x: x[1], reverse=True)
        return similar[:max_results]

    def _text_overlap_score(self, source: Page, target: Page) -> float:
        """Calculate keyword overlap between two pages."""
        source_words = set(
            (source.title or "").lower().split() +
            (source.h1 or "").lower().split()
        )
        target_words = set(
            (target.title or "").lower().split() +
            (target.h1 or "").lower().split()
        )

        if not source_words or not target_words:
            return 0.0

        # Filter stop words
        stop_words = {"in", "im", "am", "und", "oder", "mit", "für", "die", "der",
                      "das", "den", "dem", "des", "zu", "zur", "zum", "bei", "von",
                      "auf", "an", "ist", "nicht", "ein", "eine", "einen", "aus",
                      "nach", "über", "the", "and", "for", "with", "your", "our"}
        source_clean = {w for w in source_words if w not in stop_words and len(w) > 2}
        target_clean = {w for w in target_words if w not in stop_words and len(w) > 2}

        if not source_clean or not target_clean:
            return 0.0

        overlap = len(source_clean & target_clean)
        return overlap / len(source_clean | target_clean)

    def _generate_anchor(self, source: Page, target: Page) -> str:
        """Generate a natural anchor text for a link."""
        target_title = target.title or target.h1 or target.url

        # Clean up the title for anchor text
        anchor = target_title.split("|")[0].split("-")[0].strip()

        # Add context from source page
        source_topic = (source.h1 or source.title or "").lower()
        target_topic = anchor.lower()

        # If topics overlap, create contextual anchor
        if any(word in source_topic for word in target_topic.split()):
            return anchor[:80]
        else:
            return f"{anchor[:60]} im Kontext von {source_topic[:40]}"

    async def _get_existing_suggestions(self, project_id: str) -> List[InternalLinkSuggestion]:
        """Get existing link suggestions to avoid duplicates."""
        result = await self.db.execute(
            select(InternalLinkSuggestion).where(
                InternalLinkSuggestion.project_id == project_id,
            )
        )
        return result.scalars().all()
