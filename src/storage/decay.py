"""Priority decay and engram forgetting.

Automatically reduces priority of old, unused engrams and removes
stale engrams that are no longer relevant.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.storage.engrams import EngramStore


@dataclass
class DecayConfig:
    """Configuration for priority decay."""
    # Time periods (hours/days) for each tier
    working_decay_hours: int = 1
    episodic_decay_days: int = 7
    semantic_decay_days: int = 30
    procedural_decay_days: int = 90

    # Minimum confidence threshold before forgetting
    forget_threshold: float = 0.1

    # Decay rate (per day)
    decay_rate: float = 0.1

    # Max engrams per tier (for trimming)
    max_per_tier: int = 100


class PriorityDecay:
    """Manages priority decay and engram forgetting."""

    def __init__(self, store: EngramStore, config: Optional[DecayConfig] = None) -> None:
        self._store = store
        self.config = config or DecayConfig()

    def calculate_decay(self, created_at: str, category: str = "unknown") -> float:
        """Calculate decay factor for an engram based on age and category.

        Args:
            created_at: ISO timestamp of engram creation
            category: Engram category (affects decay rate)

        Returns:
            Decay factor between 0.0 (fully decayed) and 1.0 (fresh)
        """
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created = datetime.now(timezone.utc)

        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600

        # Determine decay tier based on category
        tier_hours = self._get_tier_hours(category)

        # Exponential decay
        if tier_hours > 0:
            decay = math.exp(-self.config.decay_rate * age_hours / tier_hours)
        else:
            decay = 1.0  # No decay for working tier

        return max(0.0, min(1.0, decay))

    def _get_tier_hours(self, category: str) -> float:
        """Get the tier hours for a given category."""
        category_lower = category.lower()

        # Working tier (very short-lived)
        if category_lower in ("user_correction", "debug_breakthrough"):
            return self.config.working_decay_hours

        # Episodic tier (short-term)
        if category_lower in ("user_preference", "budget_constraint"):
            return self.config.episodic_decay_days * 24

        # Semantic tier (medium-term)
        if category_lower in ("tool_discovery", "api_quirk", "error_pattern"):
            return self.config.semantic_decay_days * 24

        # Procedural tier (long-term)
        if category_lower in ("new_workflow", "architecture_decision", "project_convention"):
            return self.config.procedural_decay_days * 24

        # Default to episodic
        return self.config.episodic_decay_days * 24

    def apply_decay(self) -> dict:
        """Apply decay to all engrams.

        Reduces confidence of old engrams based on their age and category.

        Returns:
            Dict with decay statistics
        """
        all_engrams = self._store.get_all(limit=1000)
        decayed = 0
        forgotten = 0

        for engram in all_engrams:
            decay = self.calculate_decay(engram.created_at, engram.category)
            new_confidence = engram.confidence * decay

            if new_confidence < self.config.forget_threshold:
                # Forget this engram
                self._store.delete(engram.id)
                forgotten += 1
            elif new_confidence != engram.confidence:
                # Update confidence
                engram.confidence = new_confidence
                self._store.save(engram)
                decayed += 1

        return {
            "total_processed": len(all_engrams),
            "decayed": decayed,
            "forgotten": forgotten,
            "message": f"Decayed {decayed} engrams, forgotten {forgotten}",
        }

    def trim_tiers(self) -> dict:
        """Trim engrams to max_per_tier limits.

        Keeps only the most recent and highest-confidence engrams
        per tier.

        Returns:
            Dict with trim statistics
        """
        all_engrams = self._store.get_all(limit=1000)

        # Group by tier
        tiers: dict[str, list] = {
            "working": [],
            "episodic": [],
            "semantic": [],
            "procedural": [],
        }

        for engram in all_engrams:
            tier = self._get_tier_name(engram.category)
            tiers[tier].append(engram)

        trimmed = 0

        for tier_name, tier_engrams in tiers.items():
            max_count = self.config.max_per_tier
            if len(tier_engrams) > max_count:
                # Sort by confidence (desc), then recency
                tier_engrams.sort(
                    key=lambda e: (e.confidence, e.created_at),
                    reverse=True,
                )
                # Keep top N, delete the rest
                to_delete = tier_engrams[max_count:]
                for engram in to_delete:
                    self._store.delete(engram.id)
                    trimmed += 1

        return {
            "total_processed": len(all_engrams),
            "trimmed": trimmed,
            "tiers": {
                name: len(engs) for name, engs in tiers.items()
            },
        }

    def _get_tier_name(self, category: str) -> str:
        """Get the tier name for a category."""
        category_lower = category.lower()

        if category_lower in ("user_correction", "debug_breakthrough"):
            return "working"
        if category_lower in ("user_preference", "budget_constraint"):
            return "episodic"
        if category_lower in ("tool_discovery", "api_quirk", "error_pattern"):
            return "semantic"
        return "procedural"

    def get_tier_stats(self) -> dict:
        """Get statistics about engrams per tier."""
        all_engrams = self._store.get_all(limit=1000)

        tiers: dict[str, list] = {
            "working": [],
            "episodic": [],
            "semantic": [],
            "procedural": [],
        }

        for engram in all_engrams:
            tier = self._get_tier_name(engram.category)
            tiers[tier].append(engram)

        return {
            tier: {
                "count": len(engs),
                "avg_confidence": sum(e.confidence for e in engs) / len(engs) if engs else 0,
                "categories": list(set(e.category for e in engs)),
            }
            for tier, engs in tiers.items()
        }
