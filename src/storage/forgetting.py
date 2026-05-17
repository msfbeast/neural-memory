"""Engram forgetting and lifecycle management.

Handles manual and automatic forgetting of engrams based on
configurable rules and user requests.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.storage.engrams import EngramStore
from src.storage.decay import PriorityDecay
from src.storage.bm25 import get_bm25


@dataclass
class ForgettingRule:
    """Rule for automatically forgetting engrams."""
    category: str
    max_age_days: float
    min_confidence: float = 0.0
    description: str = ""


class ForgettingManager:
    """Manages engram forgetting and lifecycle."""

    def __init__(self, store: EngramStore, decay: Optional[PriorityDecay] = None) -> None:
        self._store = store
        self._decay = decay or PriorityDecay(store)
        self._rules: list[ForgettingRule] = []

        # Default rules
        self.add_rule(ForgettingRule(
            category="unknown",
            max_age_days=30,
            min_confidence=0.2,
            description="Forget unknown-category engrams older than 30 days with low confidence",
        ))
        self.add_rule(ForgettingRule(
            category="user_preference",
            max_age_days=365,
            min_confidence=0.1,
            description="Forget user preferences older than 1 year with very low confidence",
        ))

    def add_rule(self, rule: ForgettingRule) -> None:
        """Add a forgetting rule."""
        self._rules.append(rule)

    def remove_rule(self, category: str) -> None:
        """Remove a forgetting rule by category."""
        self._rules = [r for r in self._rules if r.category != category]

    def get_rules(self) -> list[dict]:
        """Get all forgetting rules."""
        return [
            {
                "category": r.category,
                "max_age_days": r.max_age_days,
                "min_confidence": r.min_confidence,
                "description": r.description,
            }
            for r in self._rules
        ]

    def apply_rules(self) -> dict:
        """Apply all forgetting rules.

        Returns:
            Dict with forgetting statistics
        """
        all_engrams = self._store.get_all(limit=1000)
        forgotten = 0
        by_rule: dict[str, int] = {}

        for engram in all_engrams:
            for rule in self._rules:
                if engram.category != rule.category:
                    continue

                # Check age
                try:
                    created = datetime.fromisoformat(engram.created_at.replace("Z", "+00:00"))
                    age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400
                except (ValueError, AttributeError):
                    age_days = 0

                if age_days > rule.max_age_days and engram.confidence <= rule.min_confidence:
                    self._store.delete(engram.id)
                    forgotten += 1
                    by_rule[rule.description] = by_rule.get(rule.description, 0) + 1
                    break

        return {
            "total_processed": len(all_engrams),
            "forgotten": forgotten,
            "by_rule": by_rule,
        }

    def forget(self, engram_id: str, reason: str = "") -> bool:
        """Manually forget (delete) an engram.

        Args:
            engram_id: ID of the engram to forget
            reason: Optional reason for forgetting

        Returns:
            True if engram was found and deleted
        """
        engram = self._store.get(engram_id)
        if not engram:
            return False

        self._store.delete(engram_id)

        if reason:
            print(f"[Forgetting] Deleted {engram_id}: {reason}")
            print(f"  Statement: {engram.statement[:100]}...")

        return True

    def forget_by_query(self, query: str, category: Optional[str] = None) -> dict:
        """Forget engrams matching a query.

        Args:
            query: Search query to find engrams
            category: Optional category filter

        Returns:
            Dict with forgetting statistics
        """
        # Use BM25 search for better matching
        try:
            bm25 = get_bm25()
            results = bm25.search(query, limit=100)
            matching_ids = set()
            for r in results:
                eid = r.get("id") if isinstance(r, dict) else r[0]
                if eid:
                    matching_ids.add(eid)
        except Exception:
            matching_ids = set()

        # Also do substring match as fallback
        if not matching_ids:
            if category:
                engrams = self._store.search_by_category(category, limit=100)
            else:
                engrams = self._store.get_all(limit=100)
            matching_ids = {e.id for e in engrams if query.lower() in e.statement.lower()}

        matching = [self._store.get(eid) for eid in matching_ids]
        matching = [e for e in matching if e is not None]

        # Apply category filter if specified
        if category:
            matching = [e for e in matching if e.category == category]

        forgotten = 0
        for engram in matching:
            self._store.delete(engram.id)
            forgotten += 1

        return {
            "query": query,
            "category": category,
            "matched": len(matching),
            "forgotten": forgotten,
        }

    def recycle_bin(self, limit: int = 50) -> list[dict]:
        """Get recently forgotten engrams (for undo).

        Note: This is a placeholder. Full recycle bin would need
        a separate storage table.

        Returns:
            List of recently forgotten engrams (empty for now)
        """
        # In a full implementation, this would query a recycle_bin table
        return []

    def restore(self, engram_id: str) -> bool:
        """Restore a forgotten engram from recycle bin.

        Args:
            engram_id: ID of the engram to restore

        Returns:
            True if restored
        """
        # Placeholder - full implementation would query recycle_bin
        print(f"[Forgetting] Restore not implemented for {engram_id}")
        return False
