"""Marketplace client — browse and download shared memories."""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from src.marketplace.cards import MemoryCard, PackCard
from src.marketplace.redactor import Redactor
from src.marketplace.packs import PackManager


# Default marketplace URL (can be overridden)
DEFAULT_MARKETPLACE_URL = "https://marketplace.neuralmemory.ai"


class MarketplaceClient:
    """Client for the NeuralMemory marketplace."""

    def __init__(
        self,
        marketplace_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.marketplace_url = marketplace_url or DEFAULT_MARKETPLACE_URL
        self.api_key = api_key
        self.redactor = Redactor()
        self.pack_manager = PackManager()

    def share_memory(
        self,
        engram_id: str,
        title: Optional[str] = None,
        author: str = "anonymous",
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Share a single memory to the marketplace.

        Returns status dict with result.
        """
        # Load engram from local store
        from src.storage.engrams import EngramStore
        store = EngramStore()
        engram = store.get(engram_id)

        if not engram:
            return {"success": False, "error": f"Engram {engram_id} not found"}

        # Mark as shared
        engram.visibility = "marketplace"
        engram.updated_at = datetime.now(timezone.utc).isoformat()
        store.save(engram)

        # Redact sensitive data
        result = self.redactor.redact(engram)

        # Generate title if not provided
        if not title:
            title = (engram.statement[:80] + "...") if len(engram.statement) > 80 else engram.statement

        # Create card
        card = MemoryCard(
            id=engram_id,
            title=title,
            statement=result.redacted_statement,
            tags=tags or engram.tags,
            category=engram.category,
            type=engram.type,
            author=author,
            created_at=engram.created_at,
            redacted=result.redacted_count > 0,
            redaction_count=result.redacted_count,
        )

        # In a real implementation, this would POST to the marketplace API
        # For now, save locally as a "shared" reference
        shared_dir = Path.home() / ".plur" / "neural_memory" / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        card_file = shared_dir / f"{engram_id}.json"
        card_file.write_text(json.dumps(card.to_dict(), indent=2))

        return {
            "success": True,
            "card": card.to_dict(),
            "redacted": result.redacted_count > 0,
            "redaction_count": result.redacted_count,
            "message": f"Memory shared as '{title}'" + (" (redacted)" if result.redacted_count > 0 else ""),
        }

    def browse_packs(
        self,
        query: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[PackCard]:
        """Browse available packs (local + marketplace)."""
        # Get local packs
        packs = self.pack_manager.list_packs()

        # In a real implementation, this would also fetch from marketplace API
        # For now, just return local packs

        # Filter by query
        if query:
            packs = [
                p for p in packs
                if query.lower() in p.name.lower() or query.lower() in p.description.lower()
            ]

        # Filter by tags
        if tags:
            packs = [
                p for p in packs
                if any(t in p.tags for t in tags)
            ]

        return packs[:limit]

    def download_pack(self, pack_id: str) -> Optional[dict]:
        """Download and install a pack.

        Returns dict with installation result.
        """
        # In a real implementation, this would fetch from marketplace API
        # For now, check local packs
        pack = self.pack_manager.get_pack(pack_id)
        if not pack:
            return {"success": False, "error": f"Pack {pack_id} not found"}

        # Import pack cards into local store
        from src.storage.engrams import EngramStore
        store = EngramStore()

        installed = []
        for card_id in pack.cards:
            # In a real implementation, fetch card details from marketplace
            # For now, skip (cards would be fetched from marketplace API)
            installed.append(card_id)

        return {
            "success": True,
            "pack": pack.to_dict(),
            "installed": installed,
            "message": f"Pack '{pack.name}' installed with {len(installed)} memories",
        }

    def list_shared(self) -> list[dict]:
        """List memories I've shared."""
        shared_dir = Path.home() / ".plur" / "neural_memory" / "shared"
        if not shared_dir.exists():
            return []

        shared = []
        for card_file in shared_dir.glob("*.json"):
            card = MemoryCard.from_dict(json.loads(card_file.read_text()))
            shared.append(card.to_dict())

        return sorted(shared, key=lambda c: c["created_at"], reverse=True)

    def unshare_memory(self, engram_id: str) -> dict:
        """Remove a memory from the marketplace."""
        from src.storage.engrams import EngramStore
        store = EngramStore()
        engram = store.get(engram_id)

        if not engram:
            return {"success": False, "error": f"Engram {engram_id} not found"}

        # Revert to private
        engram.visibility = "private"
        engram.updated_at = datetime.now(timezone.utc).isoformat()
        store.save(engram)

        # Remove shared card
        shared_dir = Path.home() / ".plur" / "neural_memory" / "shared"
        card_file = shared_dir / f"{engram_id}.json"
        if card_file.exists():
            card_file.unlink()

        return {"success": True, "message": f"Memory {engram_id} unshared"}
