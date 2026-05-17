"""Pack manager — group memories into shareable packs and recipes.

Two types of bundles:
1. Packs — simple lists of related memory IDs
2. Recipes — installable setups with instructions, dependencies, and difficulty levels

Recipes are the key innovation: someone can install a complete setup
with one click, including all related memories and step-by-step instructions.
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.marketplace.cards import MemoryCard, PackCard
from src.marketplace.recipes import Recipe, RecipeCard, rename_category


# Directory for simple packs (just lists of memory IDs)
PACKS_DIR = Path.home() / ".plur" / "neural_memory" / "packs"
# Directory for recipes (installable setups with instructions)
RECIPES_DIR = Path.home() / ".plur" / "neural_memory" / "recipes"


class PackManager:
    """Manage packs of memories for the marketplace."""

    def __init__(self, pack_dir: Optional[str] = None) -> None:
        self.pack_dir = Path(pack_dir or str(PACKS_DIR))
        self.pack_dir.mkdir(parents=True, exist_ok=True)

    def create_pack(
        self,
        name: str,
        description: str,
        card_ids: list[str],
        tags: Optional[list[str]] = None,
        author: str = "anonymous",
    ) -> PackCard:
        """Create a new pack from existing memory card IDs."""
        pack_id = f"pack-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{hashlib.sha256(name.encode()).hexdigest()[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        pack = PackCard(
            id=pack_id,
            name=name,
            description=description,
            cards=card_ids,
            tags=tags or [],
            author=author,
            created_at=now,
        )

        # Save pack metadata
        pack_file = self.pack_dir / f"{pack_id}.json"
        pack_file.write_text(json.dumps(pack.to_dict(), indent=2))

        return pack

    def get_pack(self, pack_id: str) -> Optional[PackCard]:
        """Get a pack by ID."""
        pack_file = self.pack_dir / f"{pack_id}.json"
        if not pack_file.exists():
            return None
        return PackCard.from_dict(json.loads(pack_file.read_text()))

    def list_packs(self) -> list[PackCard]:
        """List all local packs."""
        packs = []
        for pack_file in self.pack_dir.glob("*.json"):
            pack = PackCard.from_dict(json.loads(pack_file.read_text()))
            packs.append(pack)
        return sorted(packs, key=lambda p: p.created_at, reverse=True)

    def delete_pack(self, pack_id: str) -> bool:
        """Delete a pack."""
        pack_file = self.pack_dir / f"{pack_id}.json"
        if pack_file.exists():
            pack_file.unlink()
            return True
        return False

    def export_pack(self, pack_id: str, output_path: Optional[str] = None) -> Optional[str]:
        """Export a pack as a shareable JSON file."""
        pack = self.get_pack(pack_id)
        if not pack:
            return None

        if output_path is None:
            output_path = str(self.pack_dir / f"{pack_id}-export.json")

        # Include card details in export
        export_data = pack.to_dict()
        export_data["exported_at"] = datetime.now(timezone.utc).isoformat()

        Path(output_path).write_text(json.dumps(export_data, indent=2))
        return output_path

    def import_pack(self, data: dict, author: str = "anonymous") -> Optional[PackCard]:
        """Import a pack from exported data."""
        pack = PackCard.from_dict(data)
        pack.author = author  # Override author with importer
        pack.created_at = datetime.now(timezone.utc).isoformat()

        pack_file = self.pack_dir / f"{pack.id}.json"
        pack_file.write_text(json.dumps(pack.to_dict(), indent=2))
        return pack


class RecipeManager:
    """Manage installable recipes for the marketplace.

    Recipes are curated bundles of memories + setup instructions.
    Someone can install a recipe to get a complete setup running quickly.
    """

    def __init__(self, recipes_dir: Optional[str] = None) -> None:
        self.recipes_dir = Path(recipes_dir or str(RECIPES_DIR))
        self.recipes_dir.mkdir(parents=True, exist_ok=True)

    def create_recipe(
        self,
        name: str,
        description: str,
        memories: list[str],
        instructions: str,
        dependencies: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        category: str = "misc",
        difficulty: str = "beginner",
        estimated_minutes: int = 5,
        author: str = "anonymous",
    ) -> Recipe:
        """Create a new installable recipe."""
        recipe_id = f"recipe-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{hashlib.sha256(name.encode()).hexdigest()[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        recipe = Recipe(
            id=recipe_id,
            name=name,
            description=description,
            memories=memories,
            instructions=instructions,
            dependencies=dependencies or [],
            tags=tags or [],
            category=category,
            difficulty=difficulty,
            estimated_minutes=estimated_minutes,
            author=author,
            created_at=now,
        )

        # Save recipe metadata
        recipe_file = self.recipes_dir / f"{recipe_id}.json"
        recipe_file.write_text(json.dumps(recipe.to_dict(), indent=2))

        return recipe

    def get_recipe(self, recipe_id: str) -> Optional[Recipe]:
        """Get a recipe by ID."""
        recipe_file = self.recipes_dir / f"{recipe_id}.json"
        if not recipe_file.exists():
            return None
        return Recipe.from_dict(json.loads(recipe_file.read_text()))

    def list_recipes(self) -> list[Recipe]:
        """List all local recipes."""
        recipes = []
        for recipe_file in self.recipes_dir.glob("*.json"):
            recipe = Recipe.from_dict(json.loads(recipe_file.read_text()))
            recipes.append(recipe)
        return sorted(recipes, key=lambda r: r.created_at, reverse=True)

    def list_recipe_cards(self) -> list[RecipeCard]:
        """List all recipes as compact cards for browsing."""
        cards = []
        for recipe in self.list_recipes():
            cards.append(RecipeCard(
                id=recipe.id,
                name=recipe.name,
                description=recipe.description,
                category=recipe.category,
                difficulty=recipe.difficulty,
                estimated_minutes=recipe.estimated_minutes,
                author=recipe.author,
                tags=recipe.tags,
                downloads=recipe.downloads,
                rating=recipe.rating,
                verified=recipe.verified,
            ))
        return cards

    def search_recipes(self, query: Optional[str] = None, tags: Optional[list[str]] = None, category: Optional[str] = None) -> list[Recipe]:
        """Search recipes by query, tags, or category."""
        recipes = self.list_recipes()
        results = []

        for recipe in recipes:
            # Filter by category
            if category and recipe.category != category:
                continue

            # Filter by tags
            if tags and not any(t in recipe.tags for t in tags):
                continue

            # Filter by query
            if query:
                query_lower = query.lower()
                searchable = f"{recipe.name} {recipe.description} {' '.join(recipe.tags)} {recipe.instructions}".lower()
                if query_lower not in searchable:
                    continue

            results.append(recipe)

        return results

    def delete_recipe(self, recipe_id: str) -> bool:
        """Delete a recipe."""
        recipe_file = self.recipes_dir / f"{recipe_id}.json"
        if recipe_file.exists():
            recipe_file.unlink()
            return True
        return False

    def install_recipe(self, recipe_id: str) -> dict:
        """Install a recipe — copy memories and instructions to local store.

        Returns status of installation.
        """
        recipe = self.get_recipe(recipe_id)
        if not recipe:
            return {"success": False, "error": f"Recipe {recipe_id} not found"}

        # Update download count
        recipe.downloads += 1
        recipe_file = self.recipes_dir / f"{recipe_id}.json"
        recipe_file.write_text(json.dumps(recipe.to_dict(), indent=2))

        # Create a "recipe_installed" memory that records what was installed
        installed_memory = {
            "tool_name": "recipe_install",
            "input": {"recipe_id": recipe_id, "recipe_name": recipe.name},
            "output": f"Installed recipe: {recipe.name} ({len(recipe.memories)} memories)",
            "user_message": f"Installed recipe: {recipe.name}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "success": True,
            "recipe_id": recipe_id,
            "recipe_name": recipe.name,
            "memories_count": len(recipe.memories),
            "instructions": recipe.instructions,
            "dependencies": recipe.dependencies,
        }

    def export_recipe(self, recipe_id: str, output_path: Optional[str] = None) -> Optional[str]:
        """Export a recipe as a shareable JSON file."""
        recipe = self.get_recipe(recipe_id)
        if not recipe:
            return None

        if output_path is None:
            output_path = str(self.recipes_dir / f"{recipe_id}-export.json")

        export_data = recipe.to_dict()
        export_data["exported_at"] = datetime.now(timezone.utc).isoformat()

        Path(output_path).write_text(json.dumps(export_data, indent=2))
        return output_path

    def import_recipe(self, data: dict, author: str = "anonymous") -> Optional[Recipe]:
        """Import a recipe from exported data."""
        recipe = Recipe.from_dict(data)
        recipe.author = author
        recipe.created_at = datetime.now(timezone.utc).isoformat()

        recipe_file = self.recipes_dir / f"{recipe.id}.json"
        recipe_file.write_text(json.dumps(recipe.to_dict(), indent=2))
        return recipe
