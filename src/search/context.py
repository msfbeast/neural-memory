"""Session context builder — auto-summarize recent engrams.

Builds a compact context summary from recent engrams for use
in agent prompts or recall sessions.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.storage.engrams import EngramStore


class ContextBuilder:
    """Build session context from recent engrams."""

    def __init__(self, engram_store: EngramStore) -> None:
        self.engrams = engram_store

    def build_context(self, hours: int = 24, limit: int = 20,
                      include_categories: Optional[list[str]] = None,
                      exclude_categories: Optional[list[str]] = None) -> str:
        """Build a compact context summary from recent engrams.

        Args:
            hours: Lookback window in hours
            limit: Max engrams to include
            include_categories: Only include these categories
            exclude_categories: Exclude these categories

        Returns:
            Formatted context string
        """
        # Calculate time threshold
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)

        # Get recent engrams
        all_engrams = self.engrams.get_all(limit=limit * 5)

        # Filter by time
        recent = []
        for e in all_engrams:
            try:
                created = datetime.fromisoformat(e.created_at)
                if created >= cutoff:
                    recent.append(e)
            except (ValueError, TypeError):
                pass

        # Apply category filters
        if include_categories:
            recent = [e for e in recent if e.category in include_categories]
        if exclude_categories:
            recent = [e for e in recent if e.category not in exclude_categories]

        # Sort by recency
        recent.sort(key=lambda e: e.created_at, reverse=True)
        recent = recent[:limit]

        if not recent:
            return "No recent engrams found."

        # Build context string
        lines = [f"## Recent Memory ({len(recent)} engrams in last {hours}h)"]

        # Group by category
        by_category = {}
        for e in recent:
            if e.category not in by_category:
                by_category[e.category] = []
            by_category[e.category].append(e)

        for category, items in by_category.items():
            lines.append(f"\n### {category}")
            for item in items:
                short = item.statement[:120] + "..." if len(item.statement) > 120 else item.statement
                lines.append(f"- [{item.id[:12]}] {short}")

        return "\n".join(lines)

    def build_session_summary(self, session_id: str, limit: int = 50) -> str:
        """Build a summary for a specific session.

        Args:
            session_id: Session ID to summarize
            limit: Max engrams to include

        Returns:
            Formatted session summary
        """
        all_engrams = self.engrams.get_all(limit=limit * 5)

        # Filter by session
        session_engrams = [e for e in all_engrams if e.session_id == session_id]

        if not session_engrams:
            return f"No engrams found for session {session_id}"

        # Group by category
        by_category = {}
        for e in session_engrams:
            if e.category not in by_category:
                by_category[e.category] = []
            by_category[e.category].append(e)

        lines = [f"## Session Summary: {session_id}"]
        lines.append(f"Total engrams: {len(session_engrams)}")

        for category, items in by_category.items():
            lines.append(f"\n### {category} ({len(items)})")
            for item in items:
                short = item.statement[:100] + "..." if len(item.statement) > 100 else item.statement
                lines.append(f"- {short}")

        return "\n".join(lines)

    def get_recent_ids(self, hours: int = 24, limit: int = 20) -> list[str]:
        """Get IDs of recent engrams.

        Args:
            hours: Lookback window in hours
            limit: Max IDs to return

        Returns:
            List of engram IDs
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)

        all_engrams = self.engrams.get_all(limit=limit * 5)

        recent_ids = []
        for e in all_engrams:
            try:
                created = datetime.fromisoformat(e.created_at)
                if created >= cutoff:
                    recent_ids.append(e.id)
                    if len(recent_ids) >= limit:
                        break
            except (ValueError, TypeError):
                pass

        return recent_ids
