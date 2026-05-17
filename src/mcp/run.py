#!/usr/bin/env python3
"""NeuralMemory MCP Server — exposes memory operations as MCP tools.

Tools:
  memory_capture          - Capture a tool-use event as an engram
  memory_capture_batch    - Capture multiple events at once
  memory_search           - BM25 keyword search over engrams
  memory_search_hybrid    - Hybrid BM25 + vector search (RRF fusion)
  memory_similar          - Vector similarity search
  memory_recall           - Filter by category/type/domain
  memory_context          - Build compact context summary
  memory_get              - Get single engram by ID
  memory_delete           - Delete engram by ID
  memory_stats            - Memory system statistics
  memory_list             - Paginated list of all engrams
  plur_sync               - Sync NeuralMemory with PLUR
  plur_status             - PLUR sync status
  plur_load_engrams       - Load PLUR engrams into BM25 index

Usage (stdio):
    python src/mcp/server.py

Configuration:
    NEURAL_MEMORY_DIR  - Override database path (default: ~/.plur/neural_memory)
"""

import json
import sys
import os
from pathlib import Path

# Add project root to path so `from src.*` imports work
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.mcp.server import MCPHandler


def main():
    """Run MCP server over JSON-RPC 2.0 stdio."""
    handler = MCPHandler()

    # Signal initialized
    print(json.dumps({"jsonrpc": "2.0", "method": "initialized"}))
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
