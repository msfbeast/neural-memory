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
