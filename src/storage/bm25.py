"""BM25 search index using Whoosh library."""

import os
from pathlib import Path
from typing import Optional

from whoosh.index import create_in, exists_in
from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.qparser import QueryParser
from whoosh.searching import Results

from src.config import config


class BM25Index:
    """Whoosh-based BM25 search index for engrams."""

    def __init__(self, index_path: Optional[str] = None) -> None:
        self.index_path = index_path or config.get("storage.bm25_index")
        self._ensure_dirs()
        self._schema = self._create_schema()
        self._index = self._open_or_create_index()

    def _ensure_dirs(self) -> None:
        """Create index directory if it doesn't exist."""
        Path(self.index_path).mkdir(parents=True, exist_ok=True)

    def _create_schema(self) -> Schema:
        """Define the Whoosh schema."""
        return Schema(
            id=ID(stored=True, unique=True),
            statement=TEXT(stored=True),  # Default analyzer for tokenization
            type=STORED,
            category=STORED,
            domain=STORED,
            scope=STORED,
        )

    def _open_or_create_index(self):
        """Open existing index or create new one."""
        if exists_in(self.index_path):
            from whoosh.filedb.filestore import FileStorage
            storage = FileStorage(self.index_path)
            return storage.open_index()
        else:
            return create_in(self.index_path, self._schema)

    def add(self, engram_data: dict) -> None:
        """Add an engram to the BM25 index."""
        writer = self._index.writer()
        writer.add_document(
            id=engram_data["id"],
            statement=engram_data["statement"],
            type=engram_data.get("type", "behavioral"),
            category=engram_data.get("category", "unknown"),
            domain=engram_data.get("domain", ""),
            scope=engram_data.get("scope", "global"),
        )
        writer.commit()

    def delete(self, engram_id: str) -> None:
        """Remove an engram from the BM25 index."""
        writer = self._index.writer()
        writer.delete_by_term("id", engram_id)
        writer.commit()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search the BM25 index.

        Args:
            query: Search string
            limit: Max results

        Returns:
            List of result dicts with score and document
        """
        results = []
        with self._index.searcher() as searcher:
            parser = QueryParser("statement", schema=self._schema)
            parsed_query = parser.parse(query)
            search_results = searcher.search(parsed_query, limit=limit)

            for hit in search_results:
                results.append({
                    "score": float(hit.score),
                    "id": hit["id"],
                    "statement": hit["statement"],
                    "type": hit.get("type", ""),
                    "category": hit.get("category", ""),
                    "domain": hit.get("domain", ""),
                    "scope": hit.get("scope", "global"),
                })
        return results

    def search_by_category(self, category: str, limit: int = 50) -> list[dict]:
        """Search engrams by category using filtered search."""
        results = []
        with self._index.searcher() as searcher:
            parser = QueryParser("category", schema=self._schema)
            parsed_query = parser.parse(category)
            search_results = searcher.search(parsed_query, limit=limit)

            for hit in search_results:
                results.append({
                    "score": float(hit.score),
                    "id": hit["id"],
                    "statement": hit["statement"],
                    "type": hit.get("type", ""),
                    "category": hit.get("category", ""),
                    "domain": hit.get("domain", ""),
                    "scope": hit.get("scope", "global"),
                })
        return results

    def count(self) -> int:
        """Get total indexed documents."""
        with self._index.searcher() as searcher:
            return searcher.reader().doc_count()

    def refresh(self) -> None:
        """Refresh the searcher (call after bulk updates)."""
        self._index = self._open_or_create_index()


# Cached singleton
_bm25_instance: Optional[BM25Index] = None


def get_bm25() -> BM25Index:
    """Get (or create) the BM25 index singleton."""
    global _bm25_instance
    if _bm25_instance is None:
        _bm25_instance = BM25Index()
    return _bm25_instance
