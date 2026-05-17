"""SQLite engram store - PLUR-compatible persistence layer."""

import os
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import config
# Engram import moved into _row_to_engram() to avoid circular import chain:
# engrams.py → extractor.py → event_loop.py → engrams.py


class EngramStore:
    """SQLite-backed engram storage with PLUR-compatible format."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or config.get("storage.engrams_db")
        self._ensure_dirs()
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _ensure_dirs(self) -> None:
        """Create data directory if it doesn't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _create_tables(self) -> None:
        """Create engrams table if not exists."""
        self._conn.execute("""
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
        # Indexes for common queries
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_type ON engrams(type)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_scope ON engrams(scope)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_domain ON engrams(domain)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_category ON engrams(category)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_created ON engrams(created_at)")
        self._conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS engrams_fts USING fts5(statement, rationale, tags, content=engrams, content_rowid=rowid)")
        self._conn.commit()

    def save(self, engram: "Engram") -> bool:
        """Save an engram to the database."""
        try:
            tags_json = json.dumps(engram.tags)
            self._conn.execute("""
                INSERT OR REPLACE INTO engrams
                (id, statement, scope, type, domain, tags, rationale,
                 visibility, confidence, category, source_tool, session_id,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                engram.id, engram.statement, engram.scope, engram.type,
                engram.domain, tags_json, engram.rationale,
                engram.visibility, engram.confidence, engram.category,
                engram.source_tool, engram.session_id,
                engram.created_at, engram.updated_at,
            ))
            self._conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"[EngramStore] Error saving engram: {e}")
            return False

    def get(self, engram_id: str) -> Optional["Engram"]:
        """Get a single engram by ID."""
        row = self._conn.execute(
            "SELECT * FROM engrams WHERE id = ?", (engram_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_engram(dict(row))

    def get_all(self, limit: int = 100, offset: int = 0) -> list:
        """Get all engrams with pagination."""
        rows = self._conn.execute(
            "SELECT * FROM engrams ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [self._row_to_engram(dict(r)) for r in rows]

    def search_by_category(self, category: str, limit: int = 50) -> list:
        """Search engrams by category."""
        rows = self._conn.execute(
            "SELECT * FROM engrams WHERE category = ? ORDER BY created_at DESC LIMIT ?",
            (category, limit)
        ).fetchall()
        return [self._row_to_engram(dict(r)) for r in rows]

    def search_by_type(self, engram_type: str, limit: int = 50) -> list:
        """Search engrams by type."""
        rows = self._conn.execute(
            "SELECT * FROM engrams WHERE type = ? ORDER BY created_at DESC LIMIT ?",
            (engram_type, limit)
        ).fetchall()
        return [self._row_to_engram(dict(r)) for r in rows]

    def search_by_domain(self, domain: str, limit: int = 50) -> list:
        """Search engrams by domain."""
        rows = self._conn.execute(
            "SELECT * FROM engrams WHERE domain = ? ORDER BY created_at DESC LIMIT ?",
            (domain, limit)
        ).fetchall()
        return [self._row_to_engram(dict(r)) for r in rows]

    def delete(self, engram_id: str) -> bool:
        """Delete an engram by ID."""
        cursor = self._conn.execute(
            "DELETE FROM engrams WHERE id = ?", (engram_id,)
        )
        self._conn.commit()
        if cursor.rowcount > 0:
            # Sync BM25 index deletion
            try:
                from src.storage.bm25 import get_bm25
                bm25 = get_bm25()
                bm25.delete(engram_id)
            except Exception:
                pass  # Non-critical; BM25 will sync on next full rebuild
        return cursor.rowcount > 0

    def count(self) -> int:
        """Get total engram count."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM engrams").fetchone()
        return row["cnt"] if row else 0

    def stats(self) -> dict:
        """Get storage statistics."""
        total = self.count()
        by_type = {}
        for row in self._conn.execute(
            "SELECT type, COUNT(*) as cnt FROM engrams GROUP BY type"
        ).fetchall():
            by_type[row["type"]] = row["cnt"]

        by_category = {}
        for row in self._conn.execute(
            "SELECT category, COUNT(*) as cnt FROM engrams GROUP BY category"
        ).fetchall():
            by_category[row["category"]] = row["cnt"]

        return {
            "total": total,
            "by_type": by_type,
            "by_category": by_category,
        }

    def _row_to_engram(self, row: dict) -> "Engram":
        """Convert a database row to an Engram object."""
        from src.capture.extractor import Engram  # noqa: F811 - breaks circular import

        tags_str = row.get("tags", "[]")
        try:
            tags = json.loads(tags_str) if isinstance(tags_str, str) else tags_str
        except json.JSONDecodeError:
            tags = []

        return Engram(
            id=row["id"],
            statement=row["statement"],
            scope=row["scope"],
            type=row["type"],
            domain=row["domain"],
            tags=tags,
            rationale=row["rationale"],
            visibility=row["visibility"],
            confidence=row["confidence"],
            category=row["category"],
            source_tool=row["source_tool"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __del__(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
