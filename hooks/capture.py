#!/usr/bin/env python3
"""NeuralMemory PostToolUse hook for Hermes Agent.

This script runs as a shell hook on every post_tool_call event.
It captures tool events and saves meaningful ones as engrams.

Usage (registered as a shell hook in config.yaml):
    hooks:
      post_tool_call:
        - command: "python3 ~/.hermes/skills/neural-memory/hooks/capture.py"
          timeout: 5

The script reads JSON from stdin and saves engrams via the EngramStore.

Filtering: Only events matching configured patterns are saved.
Deduplication: Uses a content hash (not full event) to avoid duplicates.
Statement extraction: Builds rich, searchable statements from tool + input + result.
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
import hashlib

# Add parent dir to path so we can import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import directly from submodule files to avoid circular __init__ imports
import importlib.util
_spec = importlib.util.spec_from_file_location("engrams", str(Path(__file__).parent.parent / "src" / "storage" / "engrams.py"))
_engr_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_engr_mod)
EngramStore = _engr_mod.EngramStore

_spec2 = importlib.util.spec_from_file_location("extractor", str(Path(__file__).parent.parent / "src" / "capture" / "extractor.py"))
_ext_mod = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(_ext_mod)
Engram = _ext_mod.Engram

# Database path (same as config)
NEURAL_MEMORY_DIR = Path(os.environ.get(
    "NEURAL_MEMORY_DIR",
    str(Path.home() / ".plur" / "neural_memory")
))
CONFIG_PATH = Path(os.environ.get(
    "NEURAL_MEMORY_CONFIG",
    str(Path(__file__).parent.parent / "config.yaml")
))

# Debug mode — set NEURAL_MEMORY_DEBUG=1 to log all events to stderr
DEBUG = os.environ.get("NEURAL_MEMORY_DEBUG", "0") == "1"

# Filter patterns — which tool events are worth remembering
# Each pattern has: name, matching tools, keyword patterns to detect, and a description
FILTER_PATTERNS = [
    {
        "name": "user_correction",
        "tools": ["plur_learn", "plur_forget", "plur_promote", "plur_feedback", "memory", "skill_manage", "clarify"],
        "patterns": ["correct", "no, use", "not Y", "prefer", "always", "never", "wrong", "mistake", "fixed"],
        "description": "User corrected the agent's approach or behavior",
    },
    {
        "name": "debug_breakthrough",
        "tools": ["terminal", "execute_code", "browser_console", "session_search", "search_files"],
        "patterns": ["fix", "bug", "error", "timeout", "root cause", "traceback", "exception", "solved", "resolved", "worked", "success"],
        "description": "Debug session with a solution or discovery",
    },
    {
        "name": "tool_discovery",
        "tools": ["browser_navigate", "browser_snapshot", "browser_click", "browser_type", "browser_press", "skill_view", "skills_list"],
        "patterns": ["page loaded", "successfully", "found", "installed", "available", "registered", "working"],
        "description": "Tool discovery or setup success",
    },
    {
        "name": "user_preference",
        "tools": ["plur_learn", "plur_ingest", "memory"],
        "patterns": ["prefers", "wants", "likes", "dislikes", "avoid", "skip", "prefer", "always", "never"],
        "description": "User preference or habit",
    },
    {
        "name": "budget_constraint",
        "tools": ["terminal", "plur_learn", "browser_navigate"],
        "patterns": ["budget", "price", "₹", "rupee", "cost", "cheap", "expensive", "free", "paid", "subscription"],
        "description": "Budget or pricing constraint",
    },
    {
        "name": "file_operation",
        "tools": ["write_file", "patch", "read_file", "search_files", "file"],
        "patterns": [],  # Always capture file operations — the path itself is the signal
        "description": "Important file operations",
    },
    {
        "name": "config_change",
        "tools": ["write_file", "patch", "terminal"],
        "patterns": ["config", "yaml", "settings", "setup", "install", "pip install", "npm install", "brew install"],
        "description": "Configuration or setup changes",
    },
    {
        "name": "workflow_discovery",
        "tools": ["terminal", "execute_code", "browser_navigate", "skill_view"],
        "patterns": ["workflow", "pipeline", "process", "automate", "script", "build", "deploy", "test"],
        "description": "New workflow or process discovered",
    },
]


def get_config():
    """Load filter configuration from config.yaml or defaults."""
    config = {
        "enabled": True,
        "max_events_per_session": 100,
        "filter_patterns": [p["name"] for p in FILTER_PATTERNS],
    }

    if CONFIG_PATH.exists():
        try:
            import yaml
            with open(CONFIG_PATH) as f:
                yaml_config = yaml.safe_load(f) or {}
            if yaml_config:
                capture = yaml_config.get("capture", {})
                config["enabled"] = capture.get("enabled", True)
                config["max_events_per_session"] = capture.get("max_events_per_session", 100)
                config["filter_patterns"] = capture.get("filter_patterns", [p["name"] for p in FILTER_PATTERNS])
        except Exception:
            pass

    return config


def generate_id(tool_name: str, event: dict) -> str:
    """Generate a unique engram ID using content hash for deduplication."""
    # Use only the stable parts of the event for hashing (not timestamps)
    content = json.dumps({
        "tool": tool_name,
        "input": event.get("tool_input", {}),
        "result_preview": str(event.get("extra", {}).get("result", ""))[:200],
    }, sort_keys=True, default=str)
    hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
    date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"NM-{date_prefix}-{hash_val}"


def check_dedup(store: EngramStore, new_id: str, statement: str) -> bool:
    """Check if a near-duplicate engram already exists.
    
    Returns True if the engram should be saved (no duplicate found).
    """
    try:
        # Search for engrams with similar statements
        results = store.search(statement, limit=3)
        if not results:
            return True
        
        for existing in results:
            existing_stmt = existing.get("statement", "")
            # Exact match
            if existing_stmt == statement:
                return False
            # High similarity (same core content)
            if len(existing_stmt) > 10 and len(statement) > 10:
                # Check if one contains the other or they share >70% of key terms
                existing_terms = set(existing_stmt.lower().split())
                new_terms = set(statement.lower().split())
                if existing_terms and new_terms:
                    overlap = len(existing_terms & new_terms) / min(len(existing_terms), len(new_terms))
                    if overlap > 0.85:
                        return False
        return True
    except Exception:
        # If dedup check fails, err on the side of saving
        return True


def extract_statement(tool_name: str, event: dict) -> str:
    """Extract a human-readable, searchable statement from the event.
    
    Builds rich statements by combining tool context, input, and result.
    
    Hermes Agent sends:
    - tool_name: The tool name
    - tool_input: The args passed to the tool (dict)
    - session_id: The session ID
    - hook_event_name: The event name (e.g., "post_tool_call")
    - cwd: Current working directory
    - extra: Any extra kwargs (includes result, error, etc.)
    """
    tool_input = event.get("tool_input", {}) or {}
    extra = event.get("extra", {}) or {}
    output = extra.get("result", "") or extra.get("output", "") or ""
    error = extra.get("error", "") or ""
    cwd = event.get("cwd", "")
    
    # Try to extract meaningful content from tool_input
    if isinstance(tool_input, dict):
        # Handle plur_learn events — the statement IS the knowledge
        if tool_name == "plur_learn":
            statement = tool_input.get("statement", "")
            if statement and len(statement) > 10:
                return statement[:500]
            # If no statement field, describe what was learned
            scope = tool_input.get("scope", "")
            tags = tool_input.get("tags", [])
            if scope or tags:
                return f"Learned engram: scope={scope}, tags={tags}"
        
        # Handle plur_forget events
        if tool_name == "plur_forget":
            search = tool_input.get("search", "")
            id_val = tool_input.get("id", "")
            if search:
                return f"Forget engram matching: {search[:100]}"
            if id_val:
                return f"Forget engram by ID: {id_val[:50]}"
        
        # Handle plur_feedback events
        if tool_name == "plur_feedback":
            signal = tool_input.get("signal", "")
            engram_ids = tool_input.get("id", "") or tool_input.get("batch", [])
            if signal and engram_ids:
                return f"Feedback {signal} on engram(s): {str(engram_ids)[:80]}"
            if signal:
                return f"Feedback signal: {signal}"
        
        # Handle memory events
        if tool_name == "memory":
            action = tool_input.get("action", "")
            content = tool_input.get("content", "")
            if action and content:
                return f"Memory {action}: {content[:200]}"
        
        # Handle skill_manage events
        if tool_name == "skill_manage":
            action = tool_input.get("action", "")
            name = tool_input.get("name", "")
            if action and name:
                return f"Skill {action}: {name}"
        
        # Handle clarify events
        if tool_name == "clarify":
            question = tool_input.get("question", "")
            if question:
                return f"Asked user: {question[:200]}"
        
        # Handle terminal events — include command AND result context
        if tool_name == "terminal":
            command = tool_input.get("command", "")
            if command:
                # Build a statement that includes what the command was trying to do
                stmt = f"Terminal: {command[:200]}"
                # If there's useful output, append a summary
                if output and len(output) > 20:
                    # Take first meaningful line of output
                    first_lines = output.strip().split("\n")[:3]
                    output_preview = " ".join(l.strip() for l in first_lines if l.strip())[:150]
                    if output_preview and len(output_preview) > 5:
                        stmt += f" → {output_preview}"
                return stmt
        
        # Handle execute_code events
        if tool_name == "execute_code":
            code = tool_input.get("code", "")
            if code:
                stmt = f"Code: {code[:200]}"
                if output and len(output) > 20:
                    first_lines = output.strip().split("\n")[:3]
                    output_preview = " ".join(l.strip() for l in first_lines if l.strip())[:150]
                    if output_preview:
                        stmt += f" → {output_preview}"
                return stmt
        
        # Handle browser events
        if tool_name.startswith("browser_"):
            action = tool_name.replace("browser_", "")
            input_str = json.dumps(tool_input, default=str)[:150]
            stmt = f"Browser {action}: {input_str}"
            if output and len(output) > 20:
                first_lines = output.strip().split("\n")[:2]
                output_preview = " ".join(l.strip() for l in first_lines if l.strip())[:100]
                if output_preview:
                    stmt += f" → {output_preview}"
            return stmt
        
        # Handle write_file events
        if tool_name == "write_file":
            path = tool_input.get("path", "")
            content = tool_input.get("content", "")
            if path:
                # Try to infer what the file is from its path
                stmt = f"Write: {path}"
                # If content is short enough, include it
                if content and len(content) < 300:
                    stmt += f"\n{content[:300]}"
                return stmt
        
        # Handle patch events
        if tool_name == "patch":
            path = tool_input.get("path", "")
            old_string = tool_input.get("old_string", "")
            new_string = tool_input.get("new_string", "")
            if path:
                stmt = f"Patch: {path}"
                if old_string and new_string:
                    # Show what changed concisely
                    old_preview = old_string[:80].replace("\n", " ")
                    new_preview = new_string[:80].replace("\n", " ")
                    stmt += f"\n- {old_preview}\n+ {new_preview}"
                return stmt
        
        # Handle read_file events
        if tool_name == "read_file":
            path = tool_input.get("path", "")
            if path:
                return f"Read: {path}"
        
        # Handle search_files events
        if tool_name == "search_files":
            pattern = tool_input.get("pattern", "")
            path = tool_input.get("path", "")
            if pattern:
                stmt = f"Search: {pattern}"
                if path:
                    stmt += f" in {path}"
                return stmt
        
        # Handle session_search events
        if tool_name == "session_search":
            query = tool_input.get("query", "")
            if query:
                return f"Session search: {query[:150]}"
    
    # Fallback: use output or extra
    if output and len(output) > 10:
        # Take first meaningful chunk of output
        first_chunk = output.strip()[:300]
        return f"{tool_name}: {first_chunk}"
    
    if error and len(error) > 10:
        return f"{tool_name} error: {error[:200]}"
    
    # Last resort: describe the event
    return f"{tool_name} event (no content)"


def match_filter(tool_name: str, event: dict, config: dict):
    """Check if the event matches any filter pattern.

    Returns:
        dict with match info, or None if no match
    """
    if not config["enabled"]:
        return None

    allowed_patterns = config.get("filter_patterns", [p["name"] for p in FILTER_PATTERNS])

    for pattern in FILTER_PATTERNS:
        if pattern["name"] not in allowed_patterns:
            continue

        # Check tool match
        if tool_name not in pattern["tools"]:
            continue

        # If pattern has no keyword filters, always match (e.g., file_operation)
        if not pattern["patterns"]:
            return {
                "name": pattern["name"],
                "description": pattern["description"],
            }

        # Check content patterns against the full event text
        event_text = json.dumps(event, default=str).lower()
        for p in pattern["patterns"]:
            if p.lower() in event_text:
                return {
                    "name": pattern["name"],
                    "description": pattern["description"],
                }

    return None


def save_engram(store: EngramStore, event_id: str, category: str, confidence: float,
                statement: str, source_tool: str, session_id: str) -> bool:
    """Save an engram to the database using EngramStore."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        engram = Engram(
            id=event_id,
            statement=statement,
            scope="global",
            type="behavioral",
            domain="neural_memory",
            tags=[category],
            rationale=f"Auto-captured from {source_tool} via PostToolUse hook",
            visibility="private",
            confidence=confidence,
            category=category,
            source_tool=source_tool,
            session_id=session_id,
            created_at=now,
            updated_at=now,
        )
        return store.save(engram)
    except Exception as e:
        print(f"[NeuralMemory] Error saving engram: {e}", file=sys.stderr)
        return False


def main():
    """Main hook entry point."""
    # Read event from stdin
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[NeuralMemory] JSON decode error: {e}", file=sys.stderr)
        sys.exit(0)

    # Debug mode: log all events to stderr (only when NEURAL_MEMORY_DEBUG=1)
    if DEBUG:
        print(f"[NeuralMemory] >>> DEBUG MODE <<<", file=sys.stderr)
        print(f"[NeuralMemory] Event keys: {list(event.keys())}", file=sys.stderr)
        print(f"[NeuralMemory] Event: {json.dumps(event, default=str)[:1000]}", file=sys.stderr)

    # Extract tool info
    tool_name = event.get("tool_name", "")
    if not tool_name:
        sys.exit(0)

    # Load config
    config = get_config()

    # Check filter
    match = match_filter(tool_name, event, config)
    if not match:
        sys.exit(0)

    # Extract statement
    statement = extract_statement(tool_name, event)

    # Generate ID (uses content hash for dedup)
    event_id = generate_id(tool_name, event)

    # Deduplication check
    store = EngramStore()
    if not check_dedup(store, event_id, statement):
        sys.exit(0)

    # Save engram
    session_id = event.get("session_id", "unknown")
    if save_engram(store, event_id, match["name"], 0.95, statement, tool_name, session_id):
        print(f"[NeuralMemory] Captured: {match['name']} - {statement[:100]}", file=sys.stderr)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
