"""Auto-capture event loop.

Main entry point for capturing tool-use events and converting them to engrams.
Integrates with PLUR for bidirectional sync.
"""

import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import config
from src.capture.filters import Filter, CaptureDecision
from src.capture.extractor import Extractor, Engram
from src.storage.engrams import EngramStore
from src.storage.bm25 import BM25Index
from src.storage.vector import VectorStore
from src.bridge.plur import PLURBridge

# Configure logging
log_file = config.get("storage.log_file", "~/.plur/neural_memory/capture.log")
Path(log_file).parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("neural_memory.capture")


class EventLoop:
    """Main event loop for auto-capture with PLUR sync."""

    def __init__(self) -> None:
        self.enabled = config.get("capture.enabled", True)
        self.max_per_session = config.get("capture.max_per_session", 50)
        self.rate_limit = config.get("capture.rate_limit_per_minute", 10)

        self._filter = Filter()
        self._extractor = Extractor()
        self._store = EngramStore()
        self._bm25 = BM25Index()
        self._vector = VectorStore()
        self._plur = PLURBridge(enabled=config.get("plur.enabled", False))

        self._session_count = 0
        self._last_capture_time = 0.0
        self._minute_timestamps: list[float] = []

        # Load PLUR engrams if sync direction allows
        if self._plur.enabled:
            plur_engrams = self._plur.load_plur_engrams(limit=100)
            for pl in plur_engrams:
                self._bm25.add(pl)
                self._vector.add(pl["id"], pl["statement"])
            logger.info(f"Loaded {len(plur_engrams)} engrams from PLUR")

        logger.info("NeuralMemory EventLoop initialized")
        logger.info(f"Storage: {self._store.db_path}")
        logger.info(f"BM25 index: {self._bm25.index_path}")
        logger.info(f"Vector model: {self._vector.model_name} ({self._vector.device})")
        logger.info(f"PLUR sync: {self._plur.get_sync_config()}")

    def capture(self, event: dict) -> Optional[Engram]:
        """Process a single tool-use event.

        Args:
            event: Tool-use event dict with keys:
                - tool_name: str
                - input: dict
                - output: str
                - user_message: str (optional)
                - error: str (optional)

        Returns:
            Engram if saved, None if ignored
        """
        if not self.enabled:
            return None

        # Special handling for PLUR tool events
        tool_name = event.get("tool_name", "")
        if self._plur.enabled and self._plur.should_capture_plur_event(tool_name):
            logger.info(f"PLUR tool detected: {tool_name} — capturing for sync")

        # Rate limiting check
        if not self._check_rate_limit():
            logger.debug("Rate limited, skipping capture")
            return None

        # Session limit check
        if self._session_count >= self.max_per_session:
            logger.debug(f"Session limit reached ({self.max_per_session})")
            return None

        # Step 1: Filter
        decision = self._filter.evaluate(event)
        logger.debug(f"Filter result: {decision.reason}")

        if not decision.should_save:
            return None

        # Step 2: Extract engram
        engram = self._extractor.extract(event, decision)
        if engram is None:
            return None

        # Step 3: Save to all storage backends
        saved = self._store.save(engram)
        if saved:
            # Index for search
            self._bm25.add(engram.to_dict())
            self._vector.add(engram.id, engram.statement)

            self._session_count += 1
            logger.info(f"Saved engram: {engram.id} [{decision.category.value}]")
            logger.info(f"  Statement: {engram.statement[:100]}...")

            # Step 4: Sync to PLUR
            if self._plur.enabled:
                engram_dict = engram.to_dict()
                self._plur.capture_to_plur(engram_dict)

        return engram

    def capture_batch(self, events: list[dict]) -> list[Engram]:
        """Process multiple events at once."""
        results = []
        for event in events:
            engram = self.capture(event)
            if engram:
                results.append(engram)
        return results

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = time.time()
        # Remove timestamps older than 1 minute
        self._minute_timestamps = [
            t for t in self._minute_timestamps if now - t < 60
        ]
        if len(self._minute_timestamps) >= self.rate_limit:
            return False
        self._minute_timestamps.append(now)
        return True

    def get_stats(self) -> dict:
        """Get capture statistics."""
        return {
            "enabled": self.enabled,
            "session_count": self._session_count,
            "max_per_session": self.max_per_session,
            "rate_limit_per_minute": self.rate_limit,
            "store_stats": self._store.stats(),
            "bm25_count": self._bm25.count(),
            "vector_count": self._vector.count(),
            "vector_stats": self._vector.stats(),
            "plur_sync": self._plur.get_sync_config(),
        }

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Search across all backends (BM25 + Vector).

        Uses RRF (Reciprocal Rank Fusion) for combining results.
        """
        bm25_weight = config.get("search.bm25_weight", 0.4)
        vector_weight = config.get("search.vector_weight", 0.4)

        # BM25 results
        bm25_results = self._bm25.search(query, limit=top_k * 2)
        bm25_ranks = {r["id"]: i for i, r in enumerate(bm25_results)}

        # Vector results
        vector_results = self._vector.search(query, top_k=top_k * 2)
        vector_ranks = {r["id"]: i for i, r in enumerate(vector_results)}

        # RRF Fusion
        all_ids = set(bm25_ranks.keys()) | set(vector_ranks.keys())
        fused = []
        for engram_id in all_ids:
            bm25_rank = bm25_ranks.get(engram_id, len(all_ids))
            vector_rank = vector_ranks.get(engram_id, len(all_ids))

            score = (
                bm25_weight * (1.0 / (bm25_rank + 60)) +
                vector_weight * (1.0 / (vector_rank + 60))
            )

            # Get full engram data
            engram = self._store.get(engram_id)
            if engram:
                fused.append({
                    "id": engram_id,
                    "statement": engram.statement,
                    "score": score,
                    "type": engram.type,
                    "category": engram.category,
                    "domain": engram.domain,
                })

        # Sort by fused score
        fused.sort(key=lambda x: x["score"], reverse=True)
        return fused[:top_k]

    def close(self) -> None:
        """Clean up resources."""
        self._store.close()
        logger.info("EventLoop shut down")

    def __del__(self) -> None:
        try:
            self._store.close()
        except Exception:
            pass
