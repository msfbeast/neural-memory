"""Shareable memory cards for the marketplace.

Generates beautiful, shareable cards from engrams.
Cards are the public-facing representation of a memory.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MemoryCard:
    """A shareable card representing a single engram."""
    id: str
    title: str
    statement: str
    tags: list[str]
    category: str
    type: str
    author: str = "anonymous"
    created_at: str = ""
    downloads: int = 0
    rating: float = 0.0
    redacted: bool = False
    redaction_count: int = 0

    def to_dict(self) -> dict:
        """Serialize to dict for API/storage."""
        return {
            "id": self.id,
            "title": self.title,
            "statement": self.statement,
            "tags": self.tags,
            "category": self.category,
            "type": self.type,
            "author": self.author,
            "created_at": self.created_at,
            "downloads": self.downloads,
            "rating": self.rating,
            "redacted": self.redacted,
            "redaction_count": self.redaction_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryCard":
        """Deserialize from dict."""
        return cls(
            id=data["id"],
            title=data["title"],
            statement=data["statement"],
            tags=data.get("tags", []),
            category=data.get("category", "unknown"),
            type=data.get("type", "behavioral"),
            author=data.get("author", "anonymous"),
            created_at=data.get("created_at", ""),
            downloads=data.get("downloads", 0),
            rating=data.get("rating", 0.0),
            redacted=data.get("redacted", False),
            redaction_count=data.get("redaction_count", 0),
        )

    def to_markdown(self) -> str:
        """Generate a shareable Markdown card."""
        redacted_badge = " 🔒" if self.redacted else ""
        rating_str = f"⭐ {self.rating:.1f}" if self.rating > 0 else "⭐ New"
        downloads_str = f"📥 {self.downloads}" if self.downloads > 0 else ""

        lines = [
            f"## {self.title}{redacted_badge}",
            "",
            f"{self.statement}",
            "",
            f"**Type:** {self.type} | **Category:** {self.category}",
            f"**Rating:** {rating_str} {downloads_str}",
            "",
            f"{' '.join(f'`{t}`' for t in self.tags)}",
            "",
            "---",
            f"*Shared via NeuralMemory Marketplace*",
        ]
        return "\n".join(lines)

    def to_json_card(self) -> str:
        """Generate a compact JSON card for API responses."""
        import json
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class PackCard:
    """A pack of related memory cards."""
    id: str
    name: str
    description: str
    cards: list[str]  # List of MemoryCard IDs
    tags: list[str]
    author: str = "anonymous"
    created_at: str = ""
    downloads: int = 0
    rating: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "cards": self.cards,
            "tags": self.tags,
            "author": self.author,
            "created_at": self.created_at,
            "downloads": self.downloads,
            "rating": self.rating,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PackCard":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            cards=data.get("cards", []),
            tags=data.get("tags", []),
            author=data.get("author", "anonymous"),
            created_at=data.get("created_at", ""),
            downloads=data.get("downloads", 0),
            rating=data.get("rating", 0.0),
        )

    def to_markdown(self) -> str:
        """Generate a shareable Markdown pack card."""
        lines = [
            f"# 📦 {self.name}",
            "",
            f"{self.description}",
            "",
            f"**Author:** {self.author}",
            f"**Memories:** {len(self.cards)} | **Rating:** ⭐ {self.rating:.1f} | **Downloads:** 📥 {self.downloads}",
            "",
            f"{' '.join(f'`{t}`' for t in self.tags)}",
            "",
            "## Included Memories",
            "",
        ]
        for i, card_id in enumerate(self.cards, 1):
            lines.append(f"{i}. `{card_id}`")
        lines.extend(["", "---", "*Shared via NeuralMemory Marketplace*"])
        return "\n".join(lines)
