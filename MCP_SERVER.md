# NeuralMemory MCP Server

Expose NeuralMemory as MCP tools for Hermes Agent integration.

## Quick Start

```bash
cd /Users/msfbeast/wiki/05-tools/neural-memory
python src/mcp/run.py
```

The server reads JSON-RPC 2.0 requests from stdin and writes responses to stdout.

## Available Tools

| Tool | Description |
|------|-------------|
| `memory_capture` | Capture a tool-use event as a memory engram |
| `memory_capture_batch` | Capture multiple events at once |
| `memory_search` | BM25 keyword search over engrams |
| `memory_search_hybrid` | Hybrid BM25 + vector search (RRF fusion) |
| `memory_similar` | Vector similarity search |
| `memory_recall` | Filter by category/type/domain |
| `memory_context` | Build compact context summary |
| `memory_get` | Get single engram by ID |
| `memory_delete` | Delete engram by ID |
| `memory_stats` | Memory system statistics |
| `memory_list` | Paginated list of all engrams |
| `plur_sync` | Sync NeuralMemory with PLUR |
| `plur_status` | PLUR sync status |
| `plur_load_engrams` | Load PLUR engrams into BM25 index |

## Usage Examples

### Search engrams
```bash
echo '{"jsonrpc":"2.0","method":"memory_search","params":{"query":"debug","top_k":5},"id":1}' | python src/mcp/run.py
```

### Get stats
```bash
echo '{"jsonrpc":"2.0","method":"memory_stats","id":1}' | python src/mcp/run.py
```

### Capture an event
```bash
echo '{"jsonrpc":"2.0","method":"memory_capture","params":{"event":{"tool_name":"terminal","command":"ls","output":"file1 file2","user_message":"list files","session_id":"test","timestamp":"2026-05-17T06:00:00"}},"id":1}' | python src/mcp/run.py
```

## Configuration

- Database: `~/.plur/neural_memory/engrams.db`
- BM25 index: `~/.plur/neural_memory/bm25_index`
- Config: `src/config.py` (NEURAL_MEMORY_DIR env var override)

## Architecture

```
MCP Server (stdio, JSON-RPC 2.0)
  └── MCPHandler
       ├── EventLoop (capture + rate limiting)
       │    ├── EngramStore (SQLite)
       │    ├── BM25Index (Whoosh)
       │    ├── VectorStore (TF-IDF fallback)
       │    └── PLURBridge
       └── Tool handlers (14 methods)
```

## Status

- ✅ 14 tools registered
- ✅ Stdio protocol working
- ✅ Capture → index → search pipeline verified
- ⚠️ Vector search: TF-IDF fallback (libtorchcodec unavailable)
- ⚠️ BM25 index: 122/122 engrams indexed (analyzer fixed)
