"""Local vector embeddings using sentence-transformers."""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

from src.config import config

logger = logging.getLogger(__name__)


class VectorStore:
    """Local vector index for semantic search using sentence-transformers."""

    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None) -> None:
        self.model_name = model_name or config.get("vector.model", "all-MiniLM-L6-v2")
        self.device = device or config.get("vector.device", "cpu")
        self._model = None
        self._embeddings: Optional[np.ndarray] = None
        self._texts: list[str] = []
        self._ids: list[str] = []
        self._id_to_index: dict[str, int] = {}
        self._load_model()

    def _load_model(self) -> None:
        """Load the embedding model lazily."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name, device=self.device)
            except Exception as e:
                logger.warning("[VectorStore] Failed to load model %s: %s", self.model_name, e)
                logger.warning("[VectorStore] Falling back to TF-IDF fallback mode")
                self._model = None

    def encode(self, texts: list[str]) -> Optional[np.ndarray]:
        """Encode a list of texts into vectors."""
        if self._model is None:
            return None
        return self._model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

    def add(self, engram_id: str, statement: str) -> None:
        """Add an engram to the vector store."""
        self._ids.append(engram_id)
        self._texts.append(statement)
        self._id_to_index[engram_id] = len(self._ids) - 1

        # Re-encode all (simple approach for Phase 1)
        if self._model is not None:
            self._embeddings = self.encode(self._texts)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Search for similar texts.

        Returns:
            List of {id, statement, score} dicts
        """
        if self._model is None or self._embeddings is None:
            return []

        query_vec = self._model.encode([query], show_progress_bar=False, normalize_embeddings=True)
        query_vec = query_vec[0]  # Remove batch dim

        # Cosine similarity
        similarities = self._embeddings @ query_vec

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if similarities[idx] > 0:  # Only positive similarity
                results.append({
                    "id": self._ids[idx],
                    "statement": self._texts[idx],
                    "score": float(similarities[idx]),
                })
        return results

    def count(self) -> int:
        """Get total stored vectors."""
        return len(self._texts)

    def clear(self) -> None:
        """Clear all stored vectors."""
        self._ids = []
        self._texts = []
        self._embeddings = None
        self._id_to_index = {}

    def delete(self, engram_id: str) -> bool:
        """Remove a vector by engram ID.

        Args:
            engram_id: ID of the vector to remove

        Returns:
            True if found and removed
        """
        if engram_id not in self._id_to_index:
            return False

        idx = self._id_to_index[engram_id]
        # Remove from lists (reverse order to maintain indices)
        self._texts.pop(idx)
        self._ids.pop(idx)
        # Rebuild index
        self._id_to_index = {eid: i for i, eid in enumerate(self._ids)}
        # Rebuild embeddings
        if self._model is not None and self._texts:
            try:
                self._embeddings = self.encode(self._texts)
            except Exception:
                self._embeddings = None
        return True

    def stats(self) -> dict:
        """Get storage statistics."""
        return {
            "count": len(self._texts),
            "model": self.model_name,
            "device": self.device,
            "dimensions": self._embeddings.shape[1] if self._embeddings is not None else 0,
        }
