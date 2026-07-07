"""
Semantic keyword clustering using embedding vectors and HDBSCAN.
Groups keywords by meaning to prevent cannibalization and inform page strategy.
"""

from typing import List, Dict, Optional
from collections import defaultdict

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Keyword, KeywordCluster, Embedding


class ClusteringService:
    """
    Clusters keywords semantically using their embedding vectors.
    Falls back to text-based similarity if embeddings are not available.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def cluster_keywords(self, project: Project) -> List[KeywordCluster]:
        """Run semantic clustering on project keywords."""
        # Get keywords with embeddings
        result = await self.db.execute(
            select(Keyword).where(Keyword.project_id == project.id)
        )
        keywords = result.scalars().all()

        if len(keywords) < 2:
            return []

        # Try embedding-based clustering first
        keyword_vectors = await self._get_keyword_vectors(keywords)

        if keyword_vectors and len(keyword_vectors) >= 3:
            clusters = await self._hdbscan_cluster(keywords, keyword_vectors)
        else:
            # Fall back to text-based clustering
            clusters = await self._text_based_cluster(keywords)

        # Save clusters to database
        saved_clusters = []
        for cluster_data in clusters:
            cluster = await self._save_cluster(project.id, cluster_data)
            saved_clusters.append(cluster)

        return saved_clusters

    async def _get_keyword_vectors(self, keywords: List[Keyword]) -> Optional[Dict[str, np.ndarray]]:
        """Get embedding vectors for keywords."""
        vectors = {}
        for kw in keywords:
            result = await self.db.execute(
                select(Embedding).where(
                    Embedding.object_type == "keyword",
                    Embedding.object_id == kw.id,
                )
            )
            emb = result.scalar_one_or_none()
            if emb and emb.embedding is not None:
                vectors[kw.id] = np.array(emb.embedding, dtype=np.float32)

        return vectors if vectors else None

    async def _hdbscan_cluster(
        self,
        keywords: List[Keyword],
        vectors: Dict[str, np.ndarray],
    ) -> List[dict]:
        """Use HDBSCAN for density-based clustering of keyword vectors."""
        try:
            from hdbscan import HDBSCAN
            from sklearn.metrics.pairwise import cosine_similarity

            # Build matrix
            kw_ids = list(vectors.keys())
            matrix = np.vstack([vectors[kid] for kid in kw_ids])

            # Run HDBSCAN
            clusterer = HDBSCAN(
                min_cluster_size=2,
                min_samples=1,
                metric="euclidean",
                cluster_selection_epsilon=0.3,
            )
            labels = clusterer.fit_predict(matrix)

            # Group keywords by cluster label
            clusters = defaultdict(list)
            for kw_id, label in zip(kw_ids, labels):
                clusters[int(label)].append(kw_id)

            # Build cluster summaries
            result = []
            for label, kw_id_list in clusters.items():
                cluster_keywords = [kw for kw in keywords if kw.id in kw_id_list]
                keyword_texts = [kw.keyword for kw in cluster_keywords]

                # Find primary keyword (longest or first)
                primary = max(keyword_texts, key=len) if keyword_texts else ""

                # Calculate centroid
                if len(kw_id_list) > 0:
                    centroid = np.mean([vectors[kid] for kid in kw_id_list], axis=0)
                else:
                    centroid = None

                result.append({
                    "name": self._generate_cluster_name(keyword_texts),
                    "keywords": keyword_texts,
                    "primary_keyword": primary,
                    "cluster_size": len(keyword_texts),
                    "centroid": centroid,
                })

            return result

        except ImportError:
            return await self._text_based_cluster(keywords)

    async def _text_based_cluster(self, keywords: List[Keyword]) -> List[dict]:
        """Fallback: cluster keywords using text overlap and word similarity."""
        from collections import Counter

        # Simple bag-of-words clustering
        clusters_dict = defaultdict(list)

        for kw in keywords:
            words = set(kw.keyword.lower().split())
            # Find best matching cluster by word overlap
            best_cluster = None
            best_overlap = 0

            for cluster_key, cluster_kws in clusters_dict.items():
                cluster_words = set(cluster_key.split())
                overlap = len(words & cluster_words)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_cluster = cluster_key

            if best_overlap >= 2 and best_cluster:
                clusters_dict[best_cluster].append(kw)
            else:
                # Create new cluster key from most significant words
                significant = [w for w in words if len(w) > 3 and w not in
                              {"und", "oder", "mit", "für", "die", "der", "das", "den", "dem", "in", "im", "am"}]
                cluster_key = " ".join(significant[:3]) if significant else kw.keyword
                clusters_dict[cluster_key].append(kw)

        result = []
        for cluster_key, cluster_kws in clusters_dict.items():
            keyword_texts = [kw.keyword for kw in cluster_kws]
            primary = max(keyword_texts, key=len) if keyword_texts else ""

            result.append({
                "name": self._generate_cluster_name(keyword_texts),
                "keywords": keyword_texts,
                "primary_keyword": primary,
                "cluster_size": len(keyword_texts),
                "centroid": None,
            })

        return result

    async def _save_cluster(self, project_id: str, cluster_data: dict) -> KeywordCluster:
        """Save a keyword cluster and update keyword associations."""
        cluster = KeywordCluster(
            project_id=project_id,
            name=cluster_data["name"],
            keywords_list=cluster_data["keywords"],
            primary_keyword=cluster_data["primary_keyword"],
            cluster_size=cluster_data["cluster_size"],
        )
        self.db.add(cluster)
        await self.db.flush()

        # Update keywords to point to this cluster
        for kw_text in cluster_data["keywords"]:
            result = await self.db.execute(
                select(Keyword).where(
                    Keyword.project_id == project_id,
                    Keyword.keyword == kw_text,
                )
            )
            kw = result.scalar_one_or_none()
            if kw:
                kw.cluster_id = cluster.id

        await self.db.flush()
        return cluster

    def _generate_cluster_name(self, keyword_texts: List[str]) -> str:
        """Generate a descriptive name for a keyword cluster."""
        if not keyword_texts:
            return "Unknown Cluster"

        # Find common words
        from collections import Counter
        all_words = []
        for kw in keyword_texts:
            all_words.extend(kw.lower().split())

        # Filter stop words
        stop_words = {"in", "im", "am", "und", "oder", "mit", "für", "die", "der", "das",
                      "den", "dem", "des", "zu", "zur", "zum", "bei", "von", "auf", "an",
                      "ist", "nicht", "ein", "eine", "einen", "aus", "nach", "über"}
        filtered = [w for w in all_words if w not in stop_words and len(w) > 2]

        if not filtered:
            return keyword_texts[0][:50]

        common = Counter(filtered).most_common(5)
        return " ".join([w for w, _ in common])
