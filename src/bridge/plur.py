"""PLUR sync bridge — connect NeuralMemory to PLUR engram store.

Translates between NeuralMemory engrams and PLUR-compatible engrams.
Supports bidirectional sync: capture → PLUR learn, recall → PLUR recall.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.capture.filters import EventCategory
from src.config import config


# PLUR tool names that trigger engram capture
PLUR_TOOLS = [
    "plur_learn", "plur_ingest", "plur_feedback", "plur_forget",
    "plur_promote", "plur_extract_meta", "plur_timeline", "plur_recall",
    "plur_similarity_search", "plur_meta_submit_analysis",
]


@dataclass
class PLUREngram:
    """PLUR-compatible engram representation."""
    id: str
    statement: str
    scope: str
    engram_type: str  # behavioral, terminological, procedural, architectural
    domain: str
    tags: list[str]
    rationale: str
    visibility: str = "private"
    confidence: float = 0.8
    category: str = "unknown"
    source_tool: str = "plur"
    session_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    # PLUR-specific fields
    abstract: Optional[str] = None
    derived_from: Optional[str] = None
    knowledge_anchors: Optional[list] = None
    dual_coding: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dict for storage."""
        return {
            "id": self.id,
            "statement": self.statement,
            "scope": self.scope,
            "type": self.engram_type,
            "domain": self.domain,
            "tags": json.dumps(self.tags),
            "rationale": self.rationale,
            "visibility": self.visibility,
            "confidence": self.confidence,
            "category": self.category,
            "source_tool": self.source_tool,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class PLURBridge:
    """Bridge between NeuralMemory and PLUR systems."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._sync_enabled = config.get("plur.sync_enabled", True)
        self._sync_direction = config.get("plur.sync_direction", "both")
        # "both" = capture→PLUR + PLUR→NeuralMemory
        # "capture_only" = only capture events to PLUR
        # "recall_only" = only load PLUR engrams into NeuralMemory

    def capture_to_plur(self, engram_dict: dict) -> bool:
        """Convert a NeuralMemory engram to PLUR and call plur_learn.

        Args:
            engram_dict: NeuralMemory engram dict from EventLoop.capture()

        Returns:
            True if sync was successful
        """
        if not self.enabled or not self._sync_enabled:
            return False

        if self._sync_direction not in ("both", "capture_only"):
            return False

        try:
            # Build PLUR-compatible engram
            nm_engram = engram_dict
            nm_id = nm_engram.get("id", "")
            nm_statement = nm_engram.get("statement", "")
            nm_type = nm_engram.get("type", "behavioral")
            nm_domain = nm_engram.get("domain", "agent_session")
            nm_tags = nm_engram.get("tags", [])
            nm_rationale = nm_engram.get("rationale", "")

            # Create PLUR engram
            plur_engram = PLUREngram(
                id=nm_id,
                statement=nm_statement,
                scope=nm_engram.get("scope", "global"),
                engram_type=nm_type,
                domain=nm_domain,
                tags=nm_tags,
                rationale=nm_rationale,
                category=nm_engram.get("category", "unknown"),
                source_tool=nm_engram.get("source_tool", "neural_memory"),
                session_id=nm_engram.get("session_id"),
                created_at=nm_engram.get("created_at", datetime.now(timezone.utc).isoformat()),
                updated_at=nm_engram.get("updated_at", datetime.now(timezone.utc).isoformat()),
            )

            # Output structured marker so the agent's PostToolUse hook
            # can detect the sync and call the PLUR MCP tools directly.
            # The bridge writes a marker file that the capture hook watches.
            marker = {
                "action": "plur_sync",
                "nm_id": nm_id,
                "statement": plur_engram.statement,
                "scope": plur_engram.scope,
                "type": plur_engram.engram_type,
                "domain": plur_engram.domain,
                "tags": plur_engram.tags,
                "rationale": plur_engram.rationale,
                "visibility": plur_engram.visibility,
            }
            # Write marker to a well-known path so the capture hook can pick it up
            db_path = config.get("storage.engrams_db", "~/.plur/neural_memory/engrams.db")
            data_dir = str(Path(db_path).parent)
            Path(data_dir).mkdir(parents=True, exist_ok=True)
            marker_path = Path(data_dir) / "plur_sync_pending.json"
            # Append (don't overwrite) in case multiple syncs happen
            with open(marker_path, "a") as _f:
                _f.write(json.dumps(marker) + "\n")
            print(f"[PLURBridge] Sync marker written for engram {nm_id}")
            return True

        except Exception as e:
            print(f"[PLURBridge] Failed to sync to PLUR: {e}")
            return False

    def should_capture_plur_event(self, tool_name: str) -> bool:
        """Check if a PLUR tool event should be captured.

        Args:
            tool_name: Tool name to check

        Returns:
            True if the event should be captured
        """
        if not self.enabled:
            return False

        return tool_name in PLUR_TOOLS

    def load_plur_engrams(self, limit: int = 100) -> list[dict]:
        """Load PLUR engrams into NeuralMemory index.

        Calls plur_recall_hybrid to get relevant engrams and adds them
        to the BM25 index.

        Args:
            limit: Max engrams to load

        Returns:
            List of loaded engram dicts
        """
        if not self.enabled or self._sync_direction not in ("both", "recall_only"):
            return []

        try:
            import subprocess
            result = subprocess.run(
                [
                    "python", "-c",
                    "from hermes_tools import plur_list; print(json.dumps(plur_list(limit=200)))"
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                print(f"[PLURBridge] Failed to load PLUR engrams: {result.stderr}")
                return []

            try:
                plur_data = json.loads(result.stdout)
            except json.JSONDecodeError:
                print(f"[PLURBridge] Invalid PLUR response: {result.stdout[:200]}")
                return []

            # Convert PLUR engrams to NeuralMemory format
            loaded = []
            for item in plur_data.get("engrams", [])[:limit]:
                nm_engram = {
                    "id": item.get("id", f"plur-{uuid.uuid4().hex[:12]}"),
                    "statement": item.get("statement", ""),
                    "scope": item.get("scope", "global"),
                    "type": item.get("type", "behavioral"),
                    "domain": item.get("domain", ""),
                    "tags": item.get("tags", []),
                    "rationale": item.get("rationale", ""),
                    "visibility": item.get("visibility", "private"),
                    "confidence": item.get("confidence", 0.5),
                    "category": item.get("category", "plur_loaded"),
                    "source_tool": "plur",
                    "session_id": None,
                    "created_at": item.get("created_at", datetime.now(timezone.utc).isoformat()),
                    "updated_at": item.get("updated_at", datetime.now(timezone.utc).isoformat()),
                }
                loaded.append(nm_engram)

            print(f"[PLURBridge] Loaded {len(loaded)} engrams from PLUR")
            return loaded

        except Exception as e:
            print(f"[PLURBridge] Failed to load PLUR engrams: {e}")
            return []

    def get_sync_config(self) -> dict:
        """Get current sync configuration."""
        return {
            "enabled": self.enabled,
            "sync_enabled": self._sync_enabled,
            "sync_direction": self._sync_direction,
            "plur_tools": PLUR_TOOLS,
        }
