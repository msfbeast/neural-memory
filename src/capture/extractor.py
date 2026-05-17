"""Auto-extract engrams from tool-use events.

Converts raw capture events into PLUR-compatible engram structures.
"""

import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.capture.filters import CaptureDecision, EventCategory


@dataclass
class Engram:
    """A single engram entry, PLUR-compatible."""
    id: str
    statement: str
    scope: str = "global"
    type: str = "behavioral"  # behavioral, terminological, procedural, architectural
    domain: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    rationale: Optional[str] = None
    visibility: str = "private"
    created_at: str = ""
    updated_at: str = ""
    confidence: float = 0.0
    category: str = "unknown"
    source_tool: str = ""
    session_id: str = ""

    def to_plur_format(self) -> dict:
        """Convert to PLUR MCP tool format."""
        return {
            "statement": self.statement,
            "scope": self.scope,
            "type": self.type,
            "domain": self.domain,
            "tags": self.tags,
            "rationale": self.rationale,
            "visibility": self.visibility,
        }

    def to_dict(self) -> dict:
        """Full dict representation."""
        return {
            "id": self.id,
            "statement": self.statement,
            "scope": self.scope,
            "type": self.type,
            "domain": self.domain,
            "tags": self.tags,
            "rationale": self.rationale,
            "visibility": self.visibility,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "confidence": self.confidence,
            "category": self.category,
            "source_tool": self.source_tool,
            "session_id": self.session_id,
        }


class Extractor:
    """Extract structured engrams from raw capture events."""

    def __init__(self) -> None:
        self._session_counter = 0
        self._session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    def extract(self, event: dict, decision: CaptureDecision) -> Optional[Engram]:
        """Extract an engram from a captured event.

        Args:
            event: Raw tool-use event
            decision: Filter decision (must be should_save=True)

        Returns:
            Engram or None if extraction fails
        """
        if not decision.should_save:
            return None

        # Build the statement from event data
        statement = self._build_statement(event, decision)
        if not statement:
            return None

        # Build rationale
        rationale = self._build_rationale(event, decision)

        # Determine type based on category
        engram_type = self._category_to_type(decision.category)

        # Generate unique ID
        id_hash = hashlib.sha256(
            f"{statement}:{event.get('tool_name', '')}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]
        engram_id = f"NM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{id_hash}"

        now = datetime.now(timezone.utc).isoformat()

        return Engram(
            id=engram_id,
            statement=statement,
            type=engram_type,
            domain=self._category_to_domain(decision.category),
            tags=[decision.category.value],
            rationale=rationale,
            confidence=decision.confidence,
            category=decision.category.value,
            source_tool=event.get("tool_name", ""),
            session_id=self._session_id,
            created_at=now,
            updated_at=now,
        )

    def _build_statement(self, event: dict, decision: CaptureDecision) -> str:
        """Build a concise knowledge statement from the event."""
        tool = event.get("tool_name", "unknown")
        output = str(event.get("output", ""))[:500]  # Truncate long outputs
        user_msg = str(event.get("user_message", ""))
        error = str(event.get("error", ""))

        # Extract input/command for terminal and code events
        input_data = event.get("input", {})
        if isinstance(input_data, dict):
            command = input_data.get("command", "")
        else:
            command = str(input_data)[:300]

        # Terminal/execute_code: include the actual command executed
        if tool in ("terminal", "execute_code", "bash"):
            if command:
                return f"Terminal command: {command[:300]}"
            if output:
                return f"Terminal output: {output[:300]}"
            return f"Terminal event on {tool}: {user_msg[:200]}"

        # Category-specific statement building
        if decision.category == EventCategory.USER_CORRECTION:
            return f"User correction on {tool}: {user_msg[:200] or output[:200]}"

        if decision.category == EventCategory.DEBUG_BREAKTHROUGH:
            return f"Debug breakthrough on {tool}: {output[:300]}"

        if decision.category == EventCategory.USER_PREFERENCE:
            return f"User preference: {user_msg[:200] or output[:200]}"

        if decision.category == EventCategory.API_QUIRK:
            return f"API quirk in {tool}: {output[:300]}"

        if decision.category == EventCategory.ERROR_PATTERN:
            return f"Error pattern in {tool}: {error[:300] or output[:300]}"

        if decision.category == EventCategory.NEW_WORKFLOW:
            return f"New workflow discovered: {output[:300]}"

        if decision.category == EventCategory.TOOL_DISCOVERY:
            return f"Tool discovery: {output[:300]}"

        if decision.category == EventCategory.BUDGET_CONSTRAINT:
            return f"Budget constraint: {output[:300]}"

        if decision.category == EventCategory.PROJECT_CONVENTION:
            return f"Project convention: {output[:300]}"

        # Generic fallback
        if output:
            return f"Captured from {tool}: {output[:200]}"
        if user_msg:
            return f"Captured from {tool}: {user_msg[:200]}"
        return f"Captured from {tool}: {command[:200]}"

    def _build_rationale(self, event: dict, decision: CaptureDecision) -> str:
        """Build rationale for why this engram was saved."""
        parts = [decision.reason]
        if event.get("tool_name"):
            parts.append(f"Tool: {event['tool_name']}")
        if event.get("error"):
            parts.append(f"Error context: {str(event['error'])[:100]}")
        return "; ".join(parts)

    def _category_to_type(self, category: EventCategory) -> str:
        """Map event category to PLUR engram type."""
        mapping = {
            EventCategory.USER_CORRECTION: "behavioral",
            EventCategory.DEBUG_BREAKTHROUGH: "procedural",
            EventCategory.NEW_WORKFLOW: "procedural",
            EventCategory.ARCHITECTURE_DECISION: "architectural",
            EventCategory.API_QUIRK: "terminological",
            EventCategory.USER_PREFERENCE: "behavioral",
            EventCategory.BUDGET_CONSTRAINT: "behavioral",
            EventCategory.PROJECT_CONVENTION: "procedural",
            EventCategory.ERROR_PATTERN: "procedural",
            EventCategory.TOOL_DISCOVERY: "terminological",
        }
        return mapping.get(category, "behavioral")

    def _category_to_domain(self, category: EventCategory) -> Optional[str]:
        """Map event category to domain."""
        mapping = {
            EventCategory.API_QUIRK: "api-tools",
            EventCategory.TOOL_DISCOVERY: "tools",
            EventCategory.USER_PREFERENCE: "user",
            EventCategory.BUDGET_CONSTRAINT: "budget",
        }
        return mapping.get(category)
