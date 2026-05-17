"""Engram merging and deduplication.

Detects near-duplicate engrams and merges them, preserving the best
information from both while removing redundancy.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from src.storage.bm25 import BM25Index
from src.storage.engrams import EngramStore
from src.storage.vector import VectorStore


class EngramMerger:
    """Detect and merge similar engrams to prevent duplication."""

    def __init__(
        self,
        store: EngramStore,
        vector: VectorStore,
        bm25: BM25Index,
        similarity_threshold: float = 0.75,
        max_merged_size: int = 500,
    ) -> None:
        self._store = store
        self._vector = vector
        self._bm25 = bm25
        self.similarity_threshold = similarity_threshold
        self.max_merged_size = max_merged_size

    def find_duplicates(self, statement: str) -> list[dict]:
        """Find engrams similar to the given statement.

        Uses vector similarity as primary signal, BM25 as secondary.

        Args:
            statement: The statement to check for duplicates

        Returns:
            List of similar engrams with similarity scores
        """
        # Vector similarity search
        vector_results = self._vector.search(statement, top_k=5)

        # BM25 search as secondary signal
        bm25_results = self._bm25.search(statement, limit=5)

        # Combine results, deduplicating by ID
        seen_ids: set[str] = set()
        candidates = []

        for result in vector_results + bm25_results:
            engram_id = result.get("id", result.get("engram_id", ""))
            if engram_id and engram_id not in seen_ids:
                seen_ids.add(engram_id)
                score = result.get("score", result.get("similarity", 0))
                engram = self._store.get(engram_id)
                if engram:
                    candidates.append({
                        "id": engram_id,
                        "statement": engram.statement,
                        "score": score,
                        "type": engram.type,
                        "category": engram.category,
                        "domain": engram.domain,
                    })

        # Filter by threshold
        return [c for c in candidates if c["score"] >= self.similarity_threshold]

    def merge(
        self,
        original_id: str,
        duplicate_id: str,
        merge_strategy: str = "append",
    ) -> dict:
        """Merge a duplicate engram into the original.

        Args:
            original_id: ID of the engram to keep
            duplicate_id: ID of the engram to merge into original
            merge_strategy: "append" (add to end) or "replace" (use duplicate)

        Returns:
            Dict with merge result details
        """
        original = self._store.get(original_id)
        duplicate = self._store.get(duplicate_id)

        if not original or not duplicate:
            return {"success": False, "reason": "One or both engrams not found"}

        # Build merged statement
        if merge_strategy == "append":
            # Append duplicate info to original, avoiding repetition
            new_statement = original.statement
            # Check if duplicate statement is already contained
            if duplicate.statement not in new_statement:
                # Add as a note
                note = f" [Note: {duplicate.statement}]"
                if len(new_statement) + len(note) <= self.max_merged_size:
                    new_statement += note
                else:
                    # Truncate to max size
                    new_statement = new_statement[:self.max_merged_size - len(note) - 3] + "..."
        else:
            new_statement = duplicate.statement

        # Update original engram
        original.statement = new_statement
        original.updated_at = datetime.now(timezone.utc).isoformat()
        original.confidence = max(original.confidence, duplicate.confidence)

        # Save updated original
        self._store.save(original)

        # Delete duplicate
        self._store.delete(duplicate_id)

        # Update search indexes
        self._bm25.delete(duplicate_id)
        self._vector.delete(duplicate_id)

        return {
            "success": True,
            "merged_into": original_id,
            "removed": duplicate_id,
            "merged_statement": new_statement[:100] + "..." if len(new_statement) > 100 else new_statement,
        }

    def find_and_merge_all(
        self,
        batch_size: int = 50,
        min_confidence_after_merge: float = 0.7,
    ) -> dict:
        """Scan all engrams and merge duplicates in batches.

        Args:
            batch_size: Number of engrams to process per batch
            min_confidence_after_merge: Minimum confidence for merged engrams

        Returns:
            Dict with merge statistics
        """
        all_engrams = self._store.get_all(limit=1000)
        processed = 0
        merged_count = 0
        skipped_count = 0

        for i, engram in enumerate(all_engrams):
            if i >= batch_size:
                break

            processed += 1

            # Find duplicates
            duplicates = self.find_duplicates(engram.statement)

            if len(duplicates) > 0:
                # Merge each duplicate into the current engram
                for dup in duplicates:
                    if dup["id"] != engram.id:
                        result = self.merge(engram.id, dup["id"])
                        if result["success"]:
                            merged_count += 1
                        else:
                            skipped_count += 1

        return {
            "processed": processed,
            "merged": merged_count,
            "skipped": skipped_count,
            "message": f"Merged {merged_count} duplicates from {processed} engrams",
        }

    def dedup_index(self) -> dict:
        """Deduplicate the entire BM25 index.

        Scans all engrams, finds duplicates, merges them.

        Returns:
            Dict with deduplication statistics
        """
        return self.find_and_merge_all(batch_size=200)
