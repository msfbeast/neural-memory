"""PLUR sync consumer — processes pending markers and pushes to PLUR.

Reads plur_sync_pending.json markers and calls plur_learn via
hermes_tools to persist engrams to the real PLUR store.

Usage:
    python -m src.bridge.consumer     # process all pending markers
    python -m src.bridge.consumer --dry-run   # show what would be pushed
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import config


@dataclass
class SyncResult:
    """Result of a single sync operation."""
    engram_id: str
    success: bool
    error: Optional[str] = None
    method: str = "plur_learn"  # or "mcp"

    def to_dict(self) -> dict:
        return {
            "engram_id": self.engram_id,
            "success": self.success,
            "error": self.error,
            "method": self.method,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class PLURConsumer:
    """Process pending PLUR sync markers and push engrams to PLUR."""

    def __init__(self) -> None:
        self.marker_path = self._get_marker_path()
        self._processed_count = 0
        self._failed_count = 0
        self._skipped_count = 0

    def _get_marker_path(self) -> Path:
        """Get the path to the pending markers file."""
        db_path = config.get("storage.engrams_db", "~/.plur/neural_memory/engrams.db")
        data_dir = str(Path(db_path).parent)
        return Path(data_dir) / "plur_sync_pending.json"

    def get_pending_count(self) -> int:
        """Count pending markers without processing."""
        if not self.marker_path.exists():
            return 0
        count = 0
        with open(self.marker_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    count += 1
        return count

    def get_pending_markers(self) -> list[dict]:
        """Read all pending markers from the file."""
        if not self.marker_path.exists():
            return []

        markers = []
        with open(self.marker_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        marker = json.loads(line)
                        markers.append(marker)
                    except json.JSONDecodeError:
                        # Skip corrupt markers
                        continue
        return markers

    def _call_plur_learn(self, marker: dict) -> SyncResult:
        """Call plur_learn via hermes_tools to persist the engram.

        Uses subprocess to import hermes_tools and call plur_learn directly.
        This requires the hermes_tools module to be importable.
        """
        engram_id = marker.get("nm_id", marker.get("engram_id", "unknown"))

        # Build the plur_learn arguments
        learn_args = {
            "statement": marker.get("statement", ""),
            "scope": marker.get("scope", "global"),
            "type": marker.get("type", "behavioral"),
            "domain": marker.get("domain", ""),
            "tags": marker.get("tags", []),
            "rationale": marker.get("rationale", ""),
            "visibility": marker.get("visibility", "private"),
        }

        # Try to call plur_learn via hermes_tools subprocess
        try:
            import subprocess
            result = subprocess.run(
                [
                    sys.executable, "-c",
                    f"""
import json, sys
from hermes_tools import plur_learn
try:
    result = plur_learn(
        statement={json.dumps(learn_args["statement"])},
        scope={json.dumps(learn_args["scope"])},
        type={json.dumps(learn_args["type"])},
        domain={json.dumps(learn_args["domain"])},
        tags={json.dumps(learn_args["tags"])},
        rationale={json.dumps(learn_args["rationale"])},
        visibility={json.dumps(learn_args["visibility"])},
    )
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {{e}}", file=sys.stderr)
    sys.exit(1)
"""
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and "SUCCESS" in result.stdout:
                return SyncResult(
                    engram_id=engram_id,
                    success=True,
                )
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                return SyncResult(
                    engram_id=engram_id,
                    success=False,
                    error=f"plur_learn failed: {error_msg}",
                )

        except subprocess.TimeoutExpired:
            return SyncResult(
                engram_id=engram_id,
                success=False,
                error="plur_learn call timed out (30s)",
            )
        except FileNotFoundError:
            return SyncResult(
                engram_id=engram_id,
                success=False,
                error="hermes_tools not found — is this running inside a Hermes session?",
            )
        except Exception as e:
            return SyncResult(
                engram_id=engram_id,
                success=False,
                error=str(e),
            )

    def _call_plur_learn_via_jsonl(self, marker: dict) -> SyncResult:
        """Fallback: write a JSONL line for the agent's PostToolUse hook to process.

        When running outside a Hermes session, we can't call plur_learn directly.
        Instead, we write to a push queue that the agent's hook will pick up.
        """
        engram_id = marker.get("nm_id", marker.get("engram_id", "unknown"))
        push_queue_path = self.marker_path.parent / "plur_sync_push_pending.jsonl"

        # Write as a JSONL line with the full engram data
        push_entry = {
            "action": "plur_learn",
            "engram_id": engram_id,
            "statement": marker.get("statement", ""),
            "scope": marker.get("scope", "global"),
            "type": marker.get("type", "behavioral"),
            "domain": marker.get("domain", ""),
            "tags": marker.get("tags", []),
            "rationale": marker.get("rationale", ""),
            "visibility": marker.get("visibility", "private"),
            "source": "neural_memory_consumer",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            with open(push_queue_path, "a") as f:
                f.write(json.dumps(push_entry) + "\n")
            return SyncResult(
                engram_id=engram_id,
                success=True,
                method="push_queue",
            )
        except Exception as e:
            return SyncResult(
                engram_id=engram_id,
                success=False,
                error=f"Failed to write push queue: {e}",
            )

    def process_one(self, marker: dict) -> SyncResult:
        """Process a single marker, trying direct call first, then queue fallback."""
        # Try direct call to plur_learn
        result = self._call_plur_learn(marker)

        if result.success:
            return result

        # If direct call fails (e.g., not in Hermes session),
        # write to push queue for the agent's PostToolUse hook
        if "hermes_tools not found" in (result.error or ""):
            return self._call_plur_learn_via_jsonl(marker)

        # For other errors, still try the queue as fallback
        return self._call_plur_learn_via_jsonl(marker)

    def process_all(self, dry_run: bool = False) -> list[SyncResult]:
        """Process all pending markers.

        Args:
            dry_run: If True, show what would be done without processing

        Returns:
            List of SyncResult for each processed marker
        """
        markers = self.get_pending_markers()

        if not markers:
            print("[PLURConsumer] No pending markers to process.")
            return []

        if dry_run:
            print(f"[PLURConsumer] Dry run — {len(markers)} pending markers:")
            for i, m in enumerate(markers, 1):
                print(f"  {i}. [{m.get('nm_id', '?')}] {m.get('statement', '')[:80]}...")
            return []

        results = []
        for marker in markers:
            result = self.process_one(marker)
            results.append(result)

            if result.success:
                self._processed_count += 1
                status = "OK"
            else:
                self._failed_count += 1
                status = f"FAIL: {result.error}"
            print(f"  [{result.engram_id[:12]}] {status}")

        # Remove processed markers from the file
        if self._processed_count > 0:
            # Keep failed markers for retry, remove successful ones
            remaining = []
            for marker in markers:
                engram_id = marker.get("nm_id", marker.get("engram_id", ""))
                if not any(r.engram_id == engram_id and r.success for r in results):
                    remaining.append(marker)

            with open(self.marker_path, "w") as f:
                for marker in remaining:
                    f.write(json.dumps(marker) + "\n")

            print(f"\n[PLURConsumer] Processed {self._processed_count}, "
                  f"failed {self._failed_count}, "
                  f"{len(remaining)} remaining")
        else:
            print(f"\n[PLURConsumer] No markers processed ({self._failed_count} failures)")

        return results

    def clear_pending(self) -> int:
        """Clear all pending markers. Returns count cleared."""
        if not self.marker_path.exists():
            return 0
        count = self.get_pending_count()
        self.marker_path.unlink(missing_ok=True)
        return count

    def clear_failed(self) -> int:
        """Clear only failed markers (keep successful ones logged)."""
        if not self.marker_path.exists():
            return 0
        markers = self.get_pending_markers()
        # Keep only failed ones
        with open(self.marker_path, "w") as f:
            for marker in markers:
                f.write(json.dumps(marker) + "\n")
        return len(markers)

    def get_status(self) -> dict:
        """Get current consumer status."""
        return {
            "pending_count": self.get_pending_count(),
            "marker_path": str(self.marker_path),
            "marker_exists": self.marker_path.exists(),
        }
