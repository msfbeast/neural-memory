"""MCP server for NeuralMemory.

Provides tools for capture, search, recall, and management.
Uses JSON-RPC 2.0 over stdio.
"""

import json
import sys
import traceback
from typing import Any

from src.capture.event_loop import EventLoop
from src.config import config
from src.search.hybrid import HybridSearch
from src.search.similarity import SimilaritySearch
from src.search.context import ContextBuilder


class MCPTool:
    """MCP tool definition."""

    def __init__(self, name: str, description: str, input_schema: dict) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema


class MCPResponse:
    """MCP JSON-RPC 2.0 response."""

    def __init__(self, result: Any = None, error: dict | None = None, request_id: Any = None) -> None:
        self.result = result
        self.error = error
        self.request_id = request_id

    def to_json(self) -> str:
        """Serialize to JSON-RPC 2.0 response."""
        response = {
            "jsonrpc": "2.0",
            "id": self.request_id,
        }
        if self.error:
            response["error"] = self.error
        else:
            response["result"] = self.result
        return json.dumps(response)


class MCPHandler:
    """Handle MCP requests for NeuralMemory."""

    def __init__(self) -> None:
        self.loop = EventLoop()
        self._tools = self._register_tools()

    def _register_tools(self) -> dict[str, MCPTool]:
        """Register all available MCP tools."""
        return {
            "memory_capture": MCPTool(
                name="memory_capture",
                description="Capture a tool-use event as a memory engram. "
                           "Pass the event dict with tool_name, output, user_message, etc.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "event": {
                            "type": "object",
                            "description": "The tool-use event to capture",
                        },
                    },
                    "required": ["event"],
                },
            ),
            "memory_capture_batch": MCPTool(
                name="memory_capture_batch",
                description="Capture multiple events at once.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "events": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "List of events to capture",
                        },
                    },
                    "required": ["events"],
                },
            ),
            "memory_search": MCPTool(
                name="memory_search",
                description="Search memories using BM25 keyword search. "
                           "Returns ranked results with relevance scores.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Max results to return",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            ),
            "memory_search_hybrid": MCPTool(
                name="memory_search_hybrid",
                description="Hybrid search combining BM25 keyword + vector semantic search. "
                           "Uses Reciprocal Rank Fusion (RRF) for best-of-both-worlds recall.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Max results to return",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            ),
            "memory_similar": MCPTool(
                name="memory_similar",
                description="Find engrams similar to a given statement using vector similarity. "
                           "Returns results ranked by cosine similarity.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "statement": {
                            "type": "string",
                            "description": "Statement to find similar engrams for",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Max results to return",
                            "default": 10,
                        },
                        "min_similarity": {
                            "type": "number",
                            "description": "Minimum cosine similarity threshold (0-1)",
                            "default": 0.3,
                        },
                    },
                    "required": ["statement"],
                },
            ),
            "memory_recall": MCPTool(
                name="memory_recall",
                description="Recall memories by category, type, or domain. "
                           "Returns matching engrams.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Filter by category (e.g., user_correction, debug_breakthrough)",
                        },
                        "type": {
                            "type": "string",
                            "description": "Filter by engram type (behavioral, procedural, etc.)",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Filter by domain",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results",
                            "default": 50,
                        },
                    },
                },
            ),
            "memory_context": MCPTool(
                name="memory_context",
                description="Build a compact context summary from recent engrams. "
                           "Useful for session context or recall preparation.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "Lookback window in hours",
                            "default": 24,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max engrams to include",
                            "default": 20,
                        },
                        "include_categories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Only include these categories",
                        },
                        "exclude_categories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Exclude these categories",
                        },
                    },
                },
            ),
            "memory_get": MCPTool(
                name="memory_get",
                description="Get a single engram by its ID.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Engram ID (e.g., NM-20260516-abc123)",
                        },
                    },
                    "required": ["id"],
                },
            ),
            "memory_delete": MCPTool(
                name="memory_delete",
                description="Delete an engram by ID.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Engram ID to delete",
                        },
                    },
                    "required": ["id"],
                },
            ),
            "memory_stats": MCPTool(
                name="memory_stats",
                description="Get memory system statistics.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
            ),
            "memory_list": MCPTool(
                name="memory_list",
                description="List all stored engrams with pagination.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max results",
                            "default": 50,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Offset for pagination",
                            "default": 0,
                        },
                    },
                },
            ),
            # PLUR sync tools
            "plur_sync": MCPTool(
                name="plur_sync",
                description="Sync NeuralMemory with PLUR: load PLUR engrams into the search index "
                           "and show sync configuration. Run this periodically to keep both systems in sync.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["both", "capture_only", "recall_only"],
                            "description": "Sync direction override (optional)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max PLUR engrams to load",
                            "default": 100,
                        },
                    },
                },
            ),
            "plur_status": MCPTool(
                name="plur_status",
                description="Show PLUR sync status: enabled state, sync direction, "
                           "and tracked PLUR tool names.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
            ),
            "plur_load_engrams": MCPTool(
                name="plur_load_engrams",
                description="Manually load PLUR engrams into the NeuralMemory BM25 index. "
                           "Useful for refreshing the index with new PLUR engrams.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max engrams to load",
                            "default": 100,
                        },
                    },
                },
            ),
            "plur_push": MCPTool(
                name="plur_push",
                description="Push pending engrams from NeuralMemory to PLUR. "
                           "Reads plur_sync_pending.json markers and calls plur_learn "
                           "to persist them to the real PLUR store. "
                           "If hermes_tools is not available, writes to a push queue "
                           "for the agent's PostToolUse hook to process.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "dry_run": {
                            "type": "boolean",
                            "description": "If true, show what would be pushed without processing",
                            "default": False,
                        },
                    },
                },
            ),
            "plur_clear": MCPTool(
                name="plur_clear",
                description="Clear all pending PLUR sync markers. "
                           "Use after manual review or when markers are stale.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
            ),
            # ---- Marketplace Tools ----
            "memory_share": MCPTool(
                name="memory_share",
                description="Share a memory to the NeuralMemory marketplace. "
                           "Sensitive data is auto-redacted. Memories are private by default.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "engram_id": {
                            "type": "string",
                            "description": "Engram ID to share",
                        },
                        "title": {
                            "type": "string",
                            "description": "Optional custom title (auto-generated if omitted)",
                        },
                        "author": {
                            "type": "string",
                            "description": "Author name (default: anonymous)",
                        },
                        "tags": {
                            "type": "string",
                            "description": "Comma-separated tags",
                        },
                    },
                    "required": ["engram_id"],
                },
            ),
            "memory_unshare": MCPTool(
                name="memory_unshare",
                description="Remove a memory from the marketplace. "
                           "Reverts visibility to private.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "engram_id": {
                            "type": "string",
                            "description": "Engram ID to unshare",
                        },
                    },
                    "required": ["engram_id"],
                },
            ),
            "memory_browse_packs": MCPTool(
                name="memory_browse_packs",
                description="Browse available memory packs from the marketplace. "
                           "Search by query or filter by tags.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (optional)",
                        },
                        "tags": {
                            "type": "string",
                            "description": "Comma-separated tags to filter by",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default: 20)",
                        },
                    },
                },
            ),
            "memory_download_pack": MCPTool(
                name="memory_download_pack",
                description="Download and install a memory pack. "
                           "Installs all memories in the pack into your local store.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pack_id": {
                            "type": "string",
                            "description": "Pack ID to download",
                        },
                    },
                    "required": ["pack_id"],
                },
            ),
            "memory_list_shared": MCPTool(
                name="memory_list_shared",
                description="List memories you've shared to the marketplace.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
            ),
            "memory_create_pack": MCPTool(
                name="memory_create_pack",
                description="Create a pack from local memory cards. "
                           "Group related memories into a shareable pack.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Pack name",
                        },
                        "description": {
                            "type": "string",
                            "description": "Pack description",
                        },
                        "card_ids": {
                            "type": "string",
                            "description": "Comma-separated engram IDs to include",
                        },
                        "tags": {
                            "type": "string",
                            "description": "Comma-separated tags",
                        },
                        "author": {
                            "type": "string",
                            "description": "Author name (default: anonymous)",
                        },
                    },
                    "required": ["name", "description", "card_ids"],
                },
            ),
            # ---- Recipe Tools ----
            "recipe_create": MCPTool(
                name="recipe_create",
                description="Create an installable recipe — a curated bundle of memories "
                           "plus step-by-step setup instructions. Others can install "
                           "your recipe to get a complete setup running quickly.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Recipe name (e.g., 'Local AI Supercomputer')",
                        },
                        "description": {
                            "type": "string",
                            "description": "What this recipe sets up",
                        },
                        "memories": {
                            "type": "string",
                            "description": "Comma-separated engram IDs to include",
                        },
                        "instructions": {
                            "type": "string",
                            "description": "Step-by-step setup instructions (markdown)",
                        },
                        "dependencies": {
                            "type": "string",
                            "description": "Comma-separated list of prerequisites",
                        },
                        "tags": {
                            "type": "string",
                            "description": "Comma-separated tags for discoverability",
                        },
                        "category": {
                            "type": "string",
                            "description": "Primary category (misc, tools, workflows, etc.)",
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced"],
                            "description": "Difficulty level",
                        },
                        "estimated_minutes": {
                            "type": "integer",
                            "description": "Estimated setup time in minutes",
                        },
                        "author": {
                            "type": "string",
                            "description": "Author name (default: anonymous)",
                        },
                    },
                    "required": ["name", "description", "memories", "instructions"],
                },
            ),
            "recipe_browse": MCPTool(
                name="recipe_browse",
                description="Browse available recipes from the marketplace. "
                           "Search by query, filter by tags or category.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (optional)",
                        },
                        "tags": {
                            "type": "string",
                            "description": "Comma-separated tags to filter by",
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by category",
                        },
                    },
                },
            ),
            "recipe_install": MCPTool(
                name="recipe_install",
                description="Install a recipe — downloads memories and setup instructions. "
                           "One-click setup for complete configurations.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "recipe_id": {
                            "type": "string",
                            "description": "Recipe ID to install",
                        },
                    },
                    "required": ["recipe_id"],
                },
            ),
            "recipe_list": MCPTool(
                name="recipe_list",
                description="List all installed recipes with their details.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
            ),
            "recipe_detail": MCPTool(
                name="recipe_detail",
                description="Get full details of a recipe including instructions and dependencies.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "recipe_id": {
                            "type": "string",
                            "description": "Recipe ID to get details for",
                        },
                    },
                    "required": ["recipe_id"],
                },
            ),
        }

    def handle_request(self, request: dict) -> MCPResponse:
        """Handle an incoming MCP request.

        Args:
            request: JSON-RPC 2.0 request dict

        Returns:
            MCPResponse with result or error
        """
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            handler = getattr(self, f"_handle_{method}", None)
            if handler is None:
                return MCPResponse(
                    request_id=request_id,
                    error={"code": -32601, "message": f"Method not found: {method}"}
                )
            result = handler(params)
            return MCPResponse(result=result, request_id=request_id)
        except Exception as e:
            traceback.print_exc()
            return MCPResponse(
                request_id=request_id,
                error={"code": -32603, "message": str(e)}
            )

    def _handle_memory_capture(self, params: dict) -> dict:
        """Handle memory_capture tool."""
        event = params.get("event", {})
        engram = self.loop.capture(event)
        if engram:
            return {"success": True, "engram": engram.to_dict()}
        return {"success": False, "reason": "Event filtered out or extraction failed"}

    def _handle_memory_capture_batch(self, params: dict) -> dict:
        """Handle memory_capture_batch tool."""
        events = params.get("events", [])
        engrams = self.loop.capture_batch(events)
        return {
            "success": True,
            "captured": len(engrams),
            "engrams": [e.to_dict() for e in engrams],
        }

    def _handle_memory_search(self, params: dict) -> dict:
        """Handle memory_search tool."""
        query = params.get("query", "")
        top_k = params.get("top_k", 10)
        results = self.loop.search(query, top_k=top_k)
        return {"success": True, "results": results, "count": len(results)}

    def _handle_memory_search_hybrid(self, params: dict) -> dict:
        """Handle memory_search_hybrid tool."""
        query = params.get("query", "")
        top_k = params.get("top_k", 10)

        hybrid = HybridSearch(self.loop._store, self.loop._bm25, self.loop._vector)
        results = hybrid.search(query, limit=top_k)

        output = []
        for r in results:
            output.append({
                "id": r.engram_id,
                "statement": r.statement,
                "statement_short": r.statement_short,
                "score": r.score,
                "bm25_score": r.bm25_score,
                "vector_score": r.vector_score,
                "category": r.category,
                "tags": r.tags,
                "created_at": r.created_at,
            })

        return {"success": True, "results": output, "count": len(output)}

    def _handle_memory_similar(self, params: dict) -> dict:
        """Handle memory_similar tool."""
        statement = params.get("statement", "")
        top_k = params.get("top_k", 10)
        min_similarity = params.get("min_similarity", 0.3)

        sim = SimilaritySearch(self.loop._store, self.loop._vector, self.loop._bm25)
        results = sim.find_similar(statement, limit=top_k, min_similarity=min_similarity)

        return {"success": True, "results": results, "count": len(results)}

    def _handle_memory_recall(self, params: dict) -> dict:
        """Handle memory_recall tool."""
        category = params.get("category")
        engram_type = params.get("type")
        domain = params.get("domain")
        limit = params.get("limit", 50)

        results = []
        if category:
            results = self.loop._store.search_by_category(category, limit)
        elif engram_type:
            results = self.loop._store.search_by_type(engram_type, limit)
        elif domain:
            results = self.loop._store.search_by_domain(domain, limit)
        else:
            results = self.loop._store.get_all(limit=limit)

        return {
            "success": True,
            "results": [r.to_dict() for r in results],
            "count": len(results),
        }

    def _handle_memory_context(self, params: dict) -> dict:
        """Handle memory_context tool."""
        hours = params.get("hours", 24)
        limit = params.get("limit", 20)
        include_cats = params.get("include_categories")
        exclude_cats = params.get("exclude_categories")

        ctx = ContextBuilder(self.loop._store)
        summary = ctx.build_context(
            hours=hours,
            limit=limit,
            include_categories=include_cats,
            exclude_categories=exclude_cats,
        )

        return {"success": True, "context": summary}

    def _handle_memory_get(self, params: dict) -> dict:
        """Handle memory_get tool."""
        engram_id = params.get("id", "")
        engram = self.loop._store.get(engram_id)
        if engram:
            return {"success": True, "engram": engram.to_dict()}
        return {"success": False, "reason": f"Engram not found: {engram_id}"}

    def _handle_memory_delete(self, params: dict) -> dict:
        """Handle memory_delete tool."""
        engram_id = params.get("id", "")
        deleted = self.loop._store.delete(engram_id)
        if deleted:
            # Also remove from search indexes
            self.loop._bm25.delete(engram_id)
            return {"success": True, "deleted": engram_id}
        return {"success": False, "reason": f"Engram not found: {engram_id}"}

    def _handle_memory_stats(self, params: dict) -> dict:
        """Handle memory_stats tool."""
        return {"success": True, "stats": self.loop.get_stats()}

    def _handle_memory_list(self, params: dict) -> dict:
        """Handle memory_list tool."""
        limit = params.get("limit", 50)
        offset = params.get("offset", 0)
        engrams = self.loop._store.get_all(limit=limit, offset=offset)
        return {
            "success": True,
            "results": [e.to_dict() for e in engrams],
            "count": len(engrams),
            "total": self.loop._store.count(),
        }

    def _handle_plur_sync(self, params: dict) -> dict:
        """Handle plur_sync tool — full sync with status."""
        direction = params.get("direction")
        limit = params.get("limit", 100)

        if direction:
            self.loop._plur._sync_direction = direction

        config = self.loop._plur.get_sync_config()
        loaded = self.loop._plur.load_plur_engrams(limit=limit)

        return {
            "success": True,
            "config": config,
            "loaded_count": len(loaded),
            "message": f"Loaded {len(loaded)} engrams from PLUR",
        }

    def _handle_plur_status(self, params: dict) -> dict:
        """Handle plur_status tool."""
        config = self.loop._plur.get_sync_config()
        return {
            "success": True,
            "config": config,
        }

    def _handle_plur_load_engrams(self, params: dict) -> dict:
        """Handle plur_load_engrams tool."""
        limit = params.get("limit", 100)
        loaded = self.loop._plur.load_plur_engrams(limit=limit)
        return {
            "success": True,
            "loaded_count": len(loaded),
            "engrams": [e for e in loaded],
        }

    def _handle_plur_push(self, params: dict) -> dict:
        """Handle plur_push tool — push pending engrams to PLUR."""
        from src.bridge.consumer import PLURConsumer

        dry_run = params.get("dry_run", False)
        consumer = PLURConsumer()

        if dry_run:
            markers = consumer.get_pending_markers()
            return {
                "success": True,
                "dry_run": True,
                "pending_count": len(markers),
                "message": f"{len(markers)} pending markers found. Use dry_run=false to process.",
            }

        results = consumer.process_all()
        success_count = sum(1 for r in results if r.success)
        failed_count = sum(1 for r in results if not r.success)

        return {
            "success": True,
            "pending_count": len(results),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": [r.to_dict() for r in results],
            "message": f"Pushed {success_count}/{len(results)} engrams to PLUR",
        }

    def _handle_plur_clear(self, params: dict) -> dict:
        """Handle plur_clear tool — clear pending sync markers."""
        from src.bridge.consumer import PLURConsumer

        consumer = PLURConsumer()
        count = consumer.clear_pending()
        return {
            "success": True,
            "cleared_count": count,
            "message": f"Cleared {count} pending PLUR sync markers",
        }

    # ---- Marketplace Tools ----

    def _handle_memory_share(self, params: dict) -> dict:
        """Handle memory_share — share a memory to the marketplace."""
        from src.marketplace.client import MarketplaceClient
        client = MarketplaceClient()

        engram_id = params.get("engram_id", "")
        title = params.get("title")
        author = params.get("author", "anonymous")
        tags_str = params.get("tags", "")
        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else None

        result = client.share_memory(
            engram_id=engram_id,
            title=title,
            author=author,
            tags=tag_list,
        )
        return result

    def _handle_memory_unshare(self, params: dict) -> dict:
        """Handle memory_unshare — remove a memory from the marketplace."""
        from src.marketplace.client import MarketplaceClient
        client = MarketplaceClient()

        engram_id = params.get("engram_id", "")
        return client.unshare_memory(engram_id)

    def _handle_memory_browse_packs(self, params: dict) -> dict:
        """Handle memory_browse_packs — browse available packs."""
        from src.marketplace.client import MarketplaceClient
        client = MarketplaceClient()

        query = params.get("query", "") or None
        tags_str = params.get("tags", "")
        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else None
        limit = params.get("limit", 20)

        packs = client.browse_packs(query=query, tags=tag_list, limit=limit)
        return {
            "success": True,
            "packs": [p.to_dict() for p in packs],
            "count": len(packs),
        }

    def _handle_memory_download_pack(self, params: dict) -> dict:
        """Handle memory_download_pack — download and install a pack."""
        from src.marketplace.client import MarketplaceClient
        client = MarketplaceClient()

        pack_id = params.get("pack_id", "")
        return client.download_pack(pack_id)

    def _handle_memory_list_shared(self, params: dict) -> dict:
        """Handle memory_list_shared — list memories I've shared."""
        from src.marketplace.client import MarketplaceClient
        client = MarketplaceClient()

        shared = client.list_shared()
        return {
            "success": True,
            "shared": shared,
            "count": len(shared),
        }

    def _handle_memory_create_pack(self, params: dict) -> dict:
        """Handle memory_create_pack — create a pack from local cards."""
        from src.marketplace.client import MarketplaceClient
        client = MarketplaceClient()

        name = params.get("name", "")
        description = params.get("description", "")
        card_ids_str = params.get("card_ids", "")
        tags_str = params.get("tags", "")
        author = params.get("author", "anonymous")

        card_id_list = [c.strip() for c in card_ids_str.split(",") if c.strip()]
        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else None

        pack = client.pack_manager.create_pack(
            name=name,
            description=description,
            card_ids=card_id_list,
            tags=tag_list,
            author=author,
        )
        return {"success": True, "pack": pack.to_dict()}

    # ---- Recipe Tools ----

    def _handle_recipe_create(self, params: dict) -> dict:
        """Handle recipe_create — create an installable recipe."""
        from src.marketplace.packs import RecipeManager

        rm = RecipeManager()
        name = params.get("name", "")
        description = params.get("description", "")
        memories_str = params.get("memories", "")
        instructions = params.get("instructions", "")
        dependencies_str = params.get("dependencies", "")
        tags_str = params.get("tags", "")
        category = params.get("category", "misc")
        difficulty = params.get("difficulty", "beginner")
        estimated_minutes = params.get("estimated_minutes", 5)
        author = params.get("author", "anonymous")

        memory_list = [m.strip() for m in memories_str.split(",") if m.strip()]
        dep_list = [d.strip() for d in dependencies_str.split(",") if d.strip()] if dependencies_str else []
        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else None

        recipe = rm.create_recipe(
            name=name,
            description=description,
            memories=memory_list,
            instructions=instructions,
            dependencies=dep_list,
            tags=tag_list,
            category=category,
            difficulty=difficulty,
            estimated_minutes=estimated_minutes,
            author=author,
        )
        return {"success": True, "recipe": recipe.to_dict()}

    def _handle_recipe_browse(self, params: dict) -> dict:
        """Handle recipe_browse — browse available recipes."""
        from src.marketplace.packs import RecipeManager

        rm = RecipeManager()
        query = params.get("query", "") or None
        tags_str = params.get("tags", "")
        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else None
        category = params.get("category", None)

        recipes = rm.search_recipes(query=query, tags=tag_list, category=category)
        cards = [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "category": r.category,
                "difficulty": r.difficulty,
                "estimated_minutes": r.estimated_minutes,
                "author": r.author,
                "tags": r.tags,
                "downloads": r.downloads,
                "rating": r.rating,
                "verified": r.verified,
            }
            for r in recipes
        ]
        return {"success": True, "recipes": cards, "count": len(cards)}

    def _handle_recipe_install(self, params: dict) -> dict:
        """Handle recipe_install — install a recipe."""
        from src.marketplace.packs import RecipeManager

        rm = RecipeManager()
        recipe_id = params.get("recipe_id", "")
        return rm.install_recipe(recipe_id)

    def _handle_recipe_list(self, params: dict) -> dict:
        """Handle recipe_list — list all recipes."""
        from src.marketplace.packs import RecipeManager

        rm = RecipeManager()
        recipes = rm.list_recipes()
        return {
            "success": True,
            "recipes": [r.to_dict() for r in recipes],
            "count": len(recipes),
        }

    def _handle_recipe_detail(self, params: dict) -> dict:
        """Handle recipe_detail — get full recipe details."""
        from src.marketplace.packs import RecipeManager

        rm = RecipeManager()
        recipe_id = params.get("recipe_id", "")
        recipe = rm.get_recipe(recipe_id)
        if recipe:
            return {"success": True, "recipe": recipe.to_dict()}
        return {"success": False, "error": f"Recipe not found: {recipe_id}"}

    def list_tools(self) -> list[dict]:
        """Return list of available tool definitions."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]


def main() -> None:
    """Run MCP server over stdio."""
    handler = MCPHandler()

    print(json.dumps({
        "jsonrpc": "2.0",
        "method": "initialized",
    }))
    sys.stdout.flush()

    # List available tools
    tools = handler.list_tools()
    tool_list = []
    for tool in tools:
        tool_list.append({
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["input_schema"],
        })

    print(json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/list",
        "result": {"tools": tool_list},
    }))
    sys.stdout.flush()

    # Read requests from stdin
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handler.handle_request(request)
            print(response.to_json())
            sys.stdout.flush()
        except json.JSONDecodeError:
            print(json.dumps({
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None,
            }))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
