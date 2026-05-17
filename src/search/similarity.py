"""Similarity search — find engrams similar to a given statement.

Uses cosine similarity on stored vectors (or BM25 fallback).
"""

from typing import Optional

from src.storage.bm25 import BM25Index
from src.storage.vector import VectorStore
from src.storage.engrams import EngramStore


class SimilaritySearch:
    """Find engrams similar to a query statement."""

    def __init__(self, engram_store: EngramStore,
                 vector_store: VectorStore,
                 bm25_index: BM25Index) -> None:
        self.engrams = engram_store
        self.vector = vector_store
        self.bm25 = bm25_index

    def find_similar(self, statement: str, limit: int = 10,
                     min_similarity: float = 0.3,
                     category_filter: Optional[str] = None) -> list[dict]:
        """Find engrams similar to the given statement.

        Args:
            statement: Text to find similar engrams for
            limit: Max results
            min_similarity: Minimum cosine similarity threshold
            category_filter: Optional category filter

        Returns:
            List of {id, statement, similarity, category, tags} dicts
        """
        # Use vector search if model is loaded and has embeddings
        vector_available = (
            self.vector._model is not None
            and self.vector._embeddings is not None
            and self.vector._embeddings.shape[0] > 0
        )

        if vector_available:
            results = self.vector.search(statement, top_k=limit * 2)
        else:
            # Fallback: BM25 keyword matching with normalized scores
            bm25_results = self.bm25.search(statement, limit=limit * 2)
            if not bm25_results:
                return []
            # Normalize BM25 scores to 0-1 range
            max_score = max(r['score'] for r in bm25_results)
            results = []
            for r in bm25_results:
                engram = self.engrams.get(r['id'])
                if engram:
                    results.append({
                        'id': engram.id,
                        'statement': engram.statement,
                        'score': min(r['score'] / max(max_score, 0.01), 1.0),
                        'category': engram.category,
                        'tags': engram.tags,
                    })
            return results

        # Filter by similarity threshold
        filtered = [r for r in results if r['score'] >= min_similarity]

        # Filter by category if specified
        if category_filter:
            filtered = [r for r in filtered if r.get('category') == category_filter]

        # Sort by similarity descending
        filtered.sort(key=lambda r: r['score'], reverse=True)

        return filtered[:limit]

    def find_similar_by_id(self, engram_id: str, limit: int = 10,
                           min_similarity: float = 0.3,
                           category_filter: Optional[str] = None) -> list[dict]:
        """Find engrams similar to a specific stored engram.

        Args:
            engram_id: ID of the reference engram
            limit: Max results
            min_similarity: Minimum cosine similarity threshold
            category_filter: Optional category filter

        Returns:
            List of {id, statement, similarity, category, tags} dicts
        """
        engram = self.engrams.get(engram_id)
        if not engram:
            return []

        return self.find_similar(
            engram.statement,
            limit=limit,
            min_similarity=min_similarity,
            category_filter=category_filter,
        )
