"""Recipe-based installable packs.

Recipes are curated bundles of related memories + setup instructions
that someone can install to get a complete setup running quickly.

Unlike simple packs (just a list of memory IDs), recipes include:
- Installation instructions (what to run, what to configure)
- Dependencies (what needs to be installed first)
- Category tags for discoverability
- Difficulty level (beginner/intermediate/advanced)
- Estimated setup time
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Category mapping: old technical names → new intuitive names
CATEGORY_RENAMES = {
    "user_correction": "corrections",
    "debug_breakthrough": "debug_playbooks",
    "new_workflow": "workflows",
    "architecture_decision": "architecture",
    "api_quirk": "gotchas",
    "user_preference": "preferences",
    "budget_constraint": "budget",
    "project_convention": "conventions",
    "error_pattern": "error_patterns",
    "tool_discovery": "tools",
    "unknown": "misc",
}

# Reverse mapping for lookup
CATEGORY_REVERSE = {v: k for k, v in CATEGORY_RENAMES.items()}


@dataclass
class Recipe:
    """An installable recipe — a curated bundle of memories + setup instructions."""
    id: str
    name: str
    description: str
    memories: list[str]  # List of memory IDs to include
    instructions: str  # Installation/setup instructions (markdown)
    dependencies: list[str] = field(default_factory=list)  # What needs to be installed first
    tags: list[str] = field(default_factory=list)  # Tags for discoverability
    category: str = "misc"  # Primary category
    difficulty: str = "beginner"  # beginner, intermediate, advanced
    estimated_minutes: int = 5  # Estimated setup time
    author: str = "anonymous"
    created_at: str = ""
    downloads: int = 0
    rating: float = 0.0
    verified: bool = False  # Has this recipe been tested/verified?

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "memories": self.memories,
            "instructions": self.instructions,
            "dependencies": self.dependencies,
            "tags": self.tags,
            "category": self.category,
            "difficulty": self.difficulty,
            "estimated_minutes": self.estimated_minutes,
            "author": self.author,
            "created_at": self.created_at,
            "downloads": self.downloads,
            "rating": self.rating,
            "verified": self.verified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Recipe":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            memories=data.get("memories", []),
            instructions=data.get("instructions", ""),
            dependencies=data.get("dependencies", []),
            tags=data.get("tags", []),
            category=data.get("category", "misc"),
            difficulty=data.get("difficulty", "beginner"),
            estimated_minutes=data.get("estimated_minutes", 5),
            author=data.get("author", "anonymous"),
            created_at=data.get("created_at", ""),
            downloads=data.get("downloads", 0),
            rating=data.get("rating", 0.0),
            verified=data.get("verified", False),
        )

    def to_markdown(self) -> str:
        """Generate a shareable Markdown recipe card."""
        difficulty_emoji = {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴"}.get(self.difficulty, "⚪")
        verified_badge = " ✅ Verified" if self.verified else ""

        lines = [
            f"# {difficulty_emoji} {self.name}{verified_badge}",
            "",
            f"{self.description}",
            "",
            f"**Author:** {self.author} | **Difficulty:** {self.difficulty} | **Time:** ~{self.estimated_minutes} min",
            f"**Rating:** ⭐ {self.rating:.1f} | **Downloads:** 📥 {self.downloads}",
            "",
            "## Dependencies",
            "",
        ]
        if self.dependencies:
            for dep in self.dependencies:
                lines.append(f"- {dep}")
        else:
            lines.append("None — ready to go!")

        lines.extend([
            "",
            "## Setup Instructions",
            "",
            self.instructions,
            "",
            "## Included Memories",
            "",
        ])
        for i, mem_id in enumerate(self.memories, 1):
            lines.append(f"{i}. `{mem_id}`")

        lines.extend([
            "",
            f"{' '.join(f'`{t}`' for t in self.tags)}",
            "",
            "---",
            "*Installable via NeuralMemory Marketplace*",
        ])
        return "\n".join(lines)

    def get_install_command(self) -> str:
        """Generate a CLI command to install this recipe."""
        return f"neural-memory install {self.id}"


@dataclass
class RecipeCard:
    """A compact card for browsing recipes in the marketplace."""
    id: str
    name: str
    description: str
    category: str
    difficulty: str
    estimated_minutes: int
    author: str
    tags: list[str]
    downloads: int = 0
    rating: float = 0.0
    verified: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "difficulty": self.difficulty,
            "estimated_minutes": self.estimated_minutes,
            "author": self.author,
            "tags": self.tags,
            "downloads": self.downloads,
            "rating": self.rating,
            "verified": self.verified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecipeCard":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            category=data.get("category", "misc"),
            difficulty=data.get("difficulty", "beginner"),
            estimated_minutes=data.get("estimated_minutes", 5),
            author=data.get("author", "anonymous"),
            tags=data.get("tags", []),
            downloads=data.get("downloads", 0),
            rating=data.get("rating", 0.0),
            verified=data.get("verified", False),
        )

    def to_markdown(self) -> str:
        difficulty_emoji = {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴"}.get(self.difficulty, "⚪")
        verified_badge = " ✅" if self.verified else ""
        return (
            f"## {difficulty_emoji} {self.name}{verified_badge}\n\n"
            f"{self.description}\n\n"
            f"**{self.difficulty}** | ~{self.estimated_minutes} min | ⭐ {self.rating:.1f} | 📥 {self.downloads}\n\n"
            f"{' '.join(f'`{t}`' for t in self.tags)}"
        )


def rename_category(old_category: str) -> str:
    """Rename a technical category to its intuitive name."""
    return CATEGORY_RENAMES.get(old_category, old_category)


def get_category_label(category: str) -> str:
    """Get the display label for a category."""
    # If it's already a new name, return it
    if category in CATEGORY_RENAMES.values():
        return category
    # If it's an old name, return the new name
    return CATEGORY_RENAMES.get(category, category)
