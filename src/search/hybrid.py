"""Hybrid search — BM25 + vector RRF fusion.

Combines keyword (BM25) and semantic (vector) search results
using Reciprocal Rank Fusion (RRF) for best-of-both-worlds recall.
"""

import math
from dataclasses import dataclass
from typing import Optional

from src.storage.bm25 import BM25Index
from src.storage.vector import VectorStore
from src.storage.engrams import EngramStore


@dataclass
class SearchResult:
    """Single search result."""
    engram_id: str
    statement: str
    statement_short: str
    score: float
    bm25_score: float
    vector_score: float
    category: str
    tags: list
    created_at: str


class HybridSearch:
    """BM25 + vector RRF fusion search."""

    # RRF constant — higher = more weight on rank position
    RRF_K = 60

    def __init__(self, engram_store: EngramStore, bm25_index: BM25Index,
                 vector_store: VectorStore) -> None:
        self.engrams = engram_store
        self.bm25 = bm25_index
        self.vector = vector_store

    def search(self, query: str, limit: int = 10,
               min_score: float = 0.0,
               category_filter: Optional[str] = None) -> list[SearchResult]:
        """Hybrid search combining BM25 and vector results via RRF.

        Args:
            query: Search query
            limit: Max results to return
            min_score: Minimum fused score to include
            category_filter: Optional category to filter by

        Returns:
            List of SearchResult objects sorted by fused score
        """
        # Get BM25 results
        bm25_results = self.bm25.search(query, limit=limit * 3)

        # Get vector results
        vector_results = self.vector.search(query, top_k=limit * 3)

        # Build rank dicts: engram_id -> rank (1-indexed)
        bm25_ranks = {r['id']: i + 1 for i, r in enumerate(bm25_results)}
        vector_ranks = {r['id']: i + 1 for i, r in enumerate(vector_results)}

        # All unique engram IDs
        all_ids = set(bm25_ranks.keys()) | set(vector_ranks.keys())

        # Calculate RRF scores
        fused_scores = {}
        for eid in all_ids:
            bm25_r = bm25_ranks.get(eid, len(all_ids) + 1)
            vector_r = vector_ranks.get(eid, len(all_ids) + 1)

            bm25_rrf = 1.0 / (self.RRF_K + bm25_r)
            vector_rrf = 1.0 / (self.RRF_K + vector_r)

            # Weighted fusion — BM25 gets slightly more weight
            fused = 0.6 * bm25_rrf + 0.4 * vector_rrf
            fused_scores[eid] = {
                'score': fused,
                'bm25_rrf': bm25_rrf,
                'vector_rrf': vector_rrf,
            }

        # Filter by category if specified
        if category_filter:
            engrams_in_cat = self.engrams.search_by_category(category_filter)
            cat_ids = {e.id for e in engrams_in_cat}
            fused_scores = {
                eid: scores for eid, scores in fused_scores.items()
                if eid in cat_ids
            }

        # Sort by fused score descending
        sorted_ids = sorted(
            fused_scores.keys(),
            key=lambda eid: fused_scores[eid]['score'],
            reverse=True
        )

        # Build results
        results = []
        for eid in sorted_ids[:limit]:
            scores = fused_scores[eid]
            if scores['score'] < min_score:
                continue

            engram = self.engrams.get(eid)
            if not engram:
                continue

            short = engram.statement[:100] + "..." if len(engram.statement) > 100 else engram.statement

            results.append(SearchResult(
                engram_id=engram.id,
                statement=engram.statement,
                statement_short=short,
                score=scores['score'],
                bm25_score=scores['bm25_rrf'],
                vector_score=scores['vector_rrf'],
                category=engram.category,
                tags=engram.tags,
                created_at=engram.created_at,
            ))

        return results

    def search_bm25(self, query: str, limit: int = 10,
                    category_filter: Optional[str] = None) -> list[SearchResult]:
        """BM25-only search."""
        results = self.bm25.search(query, limit=limit)

        output = []
        for r in results:
            engram = self.engrams.get(r['id'])
            if not engram:
                continue
            short = engram.statement[:100] + "..." if len(engram.statement) > 100 else engram.statement
            output.append(SearchResult(
                engram_id=engram.id,
                statement=engram.statement,
                statement_short=short,
                score=r['score'],
                bm25_score=r['score'],
                vector_score=0.0,
                category=engram.category,
                tags=engram.tags,
                created_at=engram.created_at,
            ))
        return output

    def search_vector(self, query: str, limit: int = 10,
                      category_filter: Optional[str] = None) -> list[SearchResult]:
        """Vector-only search."""
        results = self.vector.search(query, top_k=limit)

        output = []
        for r in results:
            engram = self.engrams.get(r['id'])
            if not engram:
                continue
            short = engram.statement[:100] + "..." if len(engram.statement) > 100 else engram.statement
            output.append(SearchResult(
                engram_id=engram.id,
                statement=engram.statement,
                statement_short=short,
                score=r['score'],
                bm25_score=0.0,
                vector_score=r['score'],
                category=engram.category,
                tags=engram.tags,
                created_at=engram.created_at,
            ))
        return output
