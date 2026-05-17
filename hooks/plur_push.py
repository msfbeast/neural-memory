#!/usr/bin/env python3
"""NeuralMemory PostToolUse hook for PLUR push queue processing.

This script runs as a shell hook on every post_tool_call event.
It reads pending engram push requests from plur_sync_push_pending.jsonl
and calls plur_learn via hermes_tools for each entry.

Usage (registered as a shell hook in config.yaml):
    hooks:
      post_tool_call:
        - command: "python3 ~/.hermes/skills/neural-memory/hooks/plur_push.py"
          timeout: 10

The script reads JSONL from the push queue file and calls plur_learn
for each entry. Processed entries are removed from the queue.

This is the bridge between NeuralMemory captures and actual PLUR persistence
when running outside a direct Hermes session context.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Push queue location — same directory as the marker file
NEURAL_MEMORY_DIR = Path(os.environ.get(
    "NEURAL_MEMORY_DIR",
    str(Path.home() / ".plur" / "neural_memory")
))
PUSH_QUEUE_PATH = NEURAL_MEMORY_DIR / "plur_sync_push_pending.jsonl"

# Debug mode — set NEURAL_MEMORY_DEBUG=1 to log all events to stderr
DEBUG = os.environ.get("NEURAL_MEMORY_DEBUG", "0") == "1"

# Import plur_learn at module level so it can be mocked in tests
try:
    from hermes_tools import plur_learn
except ImportError:
    plur_learn = None  # Will be checked at runtime


def read_push_queue():
    """Read all pending entries from the push queue JSONL file.
    
    Returns:
        list[dict]: List of push queue entries
    """
    if not PUSH_QUEUE_PATH.exists():
        return []
    
    entries = []
    try:
        with open(PUSH_QUEUE_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        print(f"[NeuralMemory PLUR Push] Skipping corrupt line: {line[:100]}", file=sys.stderr)
    except Exception as e:
        print(f"[NeuralMemory PLUR Push] Error reading push queue: {e}", file=sys.stderr)
    
    return entries


def write_push_queue(entries):
    """Write the remaining entries back to the push queue JSONL file.
    
    Args:
        entries: List of entries to write
    """
    try:
        with open(PUSH_QUEUE_PATH, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[NeuralMemory PLUR Push] Error writing push queue: {e}", file=sys.stderr)


def call_plur_learn(entry):
    """Call plur_learn via hermes_tools.
    
    Args:
        entry: Push queue entry dict
        
    Returns:
        dict with success status and message
    """
    if plur_learn is None:
        return {
            "success": False,
            "message": "hermes_tools.plur_learn not available",
        }
    
    try:
        # Build the plur_learn call arguments
        args = {
            "statement": entry.get("statement", ""),
            "scope": entry.get("scope", "global"),
            "type": entry.get("type", "behavioral"),
            "domain": entry.get("domain", "neural_memory"),
            "tags": entry.get("tags", ["neural_memory", "plur_sync"]),
            "rationale": entry.get("rationale", f"Synced from NeuralMemory push queue via PostToolUse hook"),
            "visibility": entry.get("visibility", "private"),
        }
        
        # Call plur_learn
        result = plur_learn(**args)
        
        return {
            "success": True,
            "message": f"plur_learn succeeded for {entry.get('engram_id', 'unknown')}",
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"plur_learn error: {e}",
        }


def main():
    """Main hook entry point."""
    # Read event from stdin (Hermes sends JSON on every tool call)
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        # If we can't read stdin, just exit silently
        sys.exit(0)
    
    # Debug mode: log all events to stderr (only when NEURAL_MEMORY_DEBUG=1)
    if DEBUG:
        print(f"[NeuralMemory PLUR Push] >>> DEBUG MODE <<<", file=sys.stderr)
        print(f"[NeuralMemory PLUR Push] Event: {json.dumps(event, default=str)[:500]}", file=sys.stderr)
    
    # Read pending push queue entries
    entries = read_push_queue()
    
    if not entries:
        # No pending entries — exit silently (hook must be fast)
        sys.exit(0)
    
    print(f"[NeuralMemory PLUR Push] Processing {len(entries)} pending engram(s)...", file=sys.stderr)
    
    # Process each entry
    processed = []
    remaining = []
    
    for entry in entries:
        result = call_plur_learn(entry)
        
        if result["success"]:
            processed.append(entry)
            print(f"[NeuralMemory PLUR Push] OK: {entry.get('engram_id', 'unknown')} — {entry.get('statement', '')[:80]}", file=sys.stderr)
        else:
            remaining.append(entry)
            print(f"[NeuralMemory PLUR Push] FAIL: {entry.get('engram_id', 'unknown')} — {result['message']}", file=sys.stderr)
    
    # Write remaining entries back to queue
    if remaining:
        write_push_queue(remaining)
        print(f"[NeuralMemory PLUR Push] {len(remaining)} entry/entries remaining for next hook run", file=sys.stderr)
    else:
        # Remove the push queue file if all entries processed
        if PUSH_QUEUE_PATH.exists():
            PUSH_QUEUE_PATH.unlink()
            print(f"[NeuralMemory PLUR Push] Push queue cleared (all entries processed)", file=sys.stderr)
    
    # Summary
    if processed:
        print(f"[NeuralMemory PLUR Push] Processed {len(processed)} engram(s) to PLUR", file=sys.stderr)


if __name__ == "__main__":
    main()
