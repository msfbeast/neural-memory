#!/usr/bin/env python3
"""Seed the NeuralMemory database with sample engrams for dashboard testing.

Run: python scripts/seed_sample_data.py
"""

import sqlite3
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Find the engram DB path from config
project_root = Path(__file__).parent.parent
config_path = project_root / "config.yaml"

# Read config to find DB path
db_path = str(project_root / "data" / "engrams.db")
try:
    with open(config_path) as f:
        for line in f:
            if "engrams_db" in line or "engram_db" in line:
                # Extract path from config
                import re
                m = re.search(r':\s*["\']?([^\s"\']+/engrams\.db)', line)
                if m:
                    db_path = m.group(1)
                    break
except Exception:
    pass

def now():
    return datetime.now(timezone.utc).isoformat()

def days_ago(n):
    dt = datetime.now(timezone.utc) - timedelta(days=n)
    return dt.isoformat()

def seed():
    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engrams (
            id TEXT PRIMARY KEY,
            statement TEXT NOT NULL,
            scope TEXT DEFAULT 'global',
            type TEXT DEFAULT 'behavioral',
            domain TEXT,
            tags TEXT DEFAULT '[]',
            rationale TEXT,
            visibility TEXT DEFAULT 'private',
            confidence REAL DEFAULT 0.0,
            category TEXT DEFAULT 'unknown',
            source_tool TEXT,
            session_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_type ON engrams(type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_scope ON engrams(scope)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_domain ON engrams(domain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_category ON engrams(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_created ON engrams(created_at)")
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS engrams_fts USING fts5(
            statement, rationale, tags,
            content=engrams, content_rowid=rowid
        )
    """)
    conn.commit()

    samples = [
        ("seed-001",
         "macOS quarantine blocks Python on Desktop - all scripts go in ~/wiki/Scripts/ or ~/.hermes/skills/",
         "global", "behavioral", "agent_workflow",
         json.dumps(["macos", "file-placement", "quarantine"]),
         "macOS com.apple.quarantine attribute blocks Python execution on Desktop directory",
         "private", 0.95, "user_preference", "plur_learn", "session-001",
         days_ago(7), days_ago(7)),

        ("seed-002",
         "whisper.cpp with Metal is 5-10x faster than WhisperX on CPU for audio transcription",
         "global", "procedural", "audio-processing",
         json.dumps(["whisper", "metal", "performance"]),
         "Metal GPU acceleration on Apple Silicon dramatically speeds up speech recognition",
         "private", 0.90, "debug_breakthrough", "terminal", "session-002",
         days_ago(5), days_ago(5)),

        ("seed-003",
         "User creates Hindi tech content in Trakin Tech style with Hinglish titles and controversy hooks",
         "global", "behavioral", "content-creation",
         json.dumps(["hindi", "tech", "trakin-tech", "hinglish"]),
         "Content style preference for Hindi tech comparisons",
         "private", 0.95, "user_preference", "plur_learn", "session-001",
         days_ago(10), days_ago(10)),

        ("seed-004",
         "Discord API rate limits to ~5 requests per second - use 1.5s delay between creates",
         "global", "procedural", "discord-automation",
         json.dumps(["discord", "rate-limit", "api"]),
         "Discord API enforces rate limits that cause 429 errors if exceeded",
         "private", 0.85, "api_quirk", "terminal", "session-003",
         days_ago(3), days_ago(3)),

        ("seed-005",
         "PLUR engrams use domain and scope fields to namespace knowledge by project",
         "global", "terminological", "plur-memory",
         json.dumps(["plur", "engrams", "scoping"]),
         "PLUR memory system uses domain/scope for knowledge isolation",
         "private", 0.88, "new_workflow", "plur_learn", "session-004",
         days_ago(2), days_ago(2)),

        ("seed-006",
         "YouTube system includes video analysis, script generation, and competitor research modules",
         "global", "architectural", "youtube-content",
         json.dumps(["youtube", "transcript-api", "script-generation"]),
         "Complete YouTube content creation pipeline with multiple modules",
         "private", 0.82, "architecture_decision", "plur_learn", "session-005",
         days_ago(1), days_ago(1)),

        ("seed-007",
         "Content DNA uses 5-pillar viral formula: relatability, character archetypes, emotional whiplash, cultural shorthand, Hinglish",
         "global", "procedural", "content-creation",
         json.dumps(["viral-formula", "content-dna", "scripting"]),
         "Proven formula for viral Hindi short-form content",
         "private", 0.92, "new_workflow", "plur_learn", "session-006",
         days_ago(4), days_ago(4)),

        ("seed-008",
         "LM Studio needs 3600+ second timeout for long-running local LLM tasks to avoid connection resets",
         "global", "behavioral", "local-llm",
         json.dumps(["lm-studio", "timeout", "local-llm"]),
         "Default 180s timeout too short for 35B parameter model inference",
         "private", 0.87, "error_pattern", "terminal", "session-007",
         days_ago(6), days_ago(6)),

        ("seed-009",
         "NeuralMemory pipeline: EventLoop -> Filter -> Extractor -> EngramStore -> BM25Index -> Search",
         "global", "architectural", "neural-memory",
         json.dumps(["pipeline", "architecture", "capture"]),
         "Core data flow for auto-capture of agent session knowledge",
         "private", 0.90, "architecture_decision", "plur_learn", "session-008",
         now(), now()),

        ("seed-010",
         "Streamlit dashboard for NeuralMemory: overview stats, BM25 search, filters, detail view, delete",
         "global", "procedural", "neural-memory",
         json.dumps(["streamlit", "dashboard", "ui"]),
         "Web UI for viewing and managing captured engrams",
         "private", 0.85, "tool_discovery", "plur_learn", "session-009",
         now(), now()),
    ]

    count = 0
    for s in samples:
        conn.execute("""
            INSERT OR REPLACE INTO engrams
            (id, statement, scope, type, domain, tags, rationale,
             visibility, confidence, category, source_tool, session_id,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, s)
        count += 1

    conn.commit()
    conn.close()

    print(f"Seeded {count} engrams into {db_path}")

    # Verify
    conn = sqlite3.connect(db_path)
    total = conn.execute("SELECT COUNT(*) FROM engrams").fetchone()[0]
    by_type = conn.execute("SELECT type, COUNT(*) FROM engrams GROUP BY type").fetchall()
    by_cat = conn.execute("SELECT category, COUNT(*) FROM engrams GROUP BY category").fetchall()
    conn.close()

    print(f"Total engrams in DB: {total}")
    print(f"By type: {dict(by_type)}")
    print(f"By category: {dict(by_cat)}")

if __name__ == "__main__":
    seed()
