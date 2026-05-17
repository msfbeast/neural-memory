# NeuralMemory Progress Tracker

## Session: MCP Server Build
**Date**: 2026-05-17
**Status**: ✅ MCP Server complete (14 tools, stdio protocol)

## What Was Built

### MCP Server (`src/mcp/server.py` + `src/mcp/run.py`)
- **14 tools** registered over JSON-RPC 2.0 stdio
- Entry point: `python src/mcp/run.py`
- Tools: memory_capture, memory_capture_batch, memory_search, memory_search_hybrid, memory_similar, memory_recall, memory_context, memory_get, memory_delete, memory_stats, memory_list, plur_sync, plur_status, plur_load_engrams

### BM25 Index Fix
- Fixed `analyzer=None` → default Whoosh analyzer for proper tokenization
- Reindexed all 122 engrams
- Search now works: "terminal" → 2 results, "hello world" → 1 result

### Integration Tests
- Capture → BM25 index → search pipeline verified end-to-end
- Stdio protocol tested: echo '{"jsonrpc":"2.0","method":"memory_stats","id":1}' | python src/mcp/run.py
- Full capture test: event → engram → stored → indexed → searchable

## Current Architecture

```
EventLoop (capture + rate limiting)
  ├── EngramStore (SQLite)
  ├── BM25Index (Whoosh) — 122 docs indexed
  ├── VectorStore (TF-IDF fallback, FAISS unavailable)
  └── PLURBridge (disabled, no external deps)

MCP Server (stdio)
  └── 16 tools → EventLoop methods

Streamlit Dashboard (http://localhost:8507)
  └── Reads from same SQLite DB
  └── 6 tabs: Overview, Search, All Engrams, Detail View, Marketplace & Recipes, PLUR Sync
```

## PLUR Consumer (2026-05-17)

### What Was Built

**`src/bridge/consumer.py`** — Processes pending markers and pushes to PLUR
- `get_pending_count()` — count pending markers without processing
- `get_pending_markers()` — read all pending markers from JSONL file
- `process_all(dry_run=False)` — process all pending markers
- `process_one(marker)` — process single marker (tries direct call, falls back to queue)
- `clear_pending()` — clear all pending markers
- Two-tier approach:
  1. **Direct**: calls `plur_learn` via `hermes_tools` subprocess (when in Hermes session)
  2. **Fallback**: writes to `plur_sync_push_pending.jsonl` for PostToolUse hook to process

**New CLI commands**:
- `neural-memory plur-push` — push pending engrams to PLUR
- `neural-memory plur-push --dry-run` — show what would be pushed
- `neural-memory plur-clear` — clear all pending markers

**New MCP tools**:
- `plur_push` — push pending engrams (with dry_run support)
- `plur_clear` — clear pending markers

**Dashboard tab**: "PLUR Sync" with:
- Pending markers counter + sync config metrics
- Expandable pending marker details
- Push All / Dry Run / Clear All buttons
- Push Queue (PostToolUse Hook) status

**Tests**: 6 new tests, all passing
- `test_consumer_get_pending_empty`
- `test_consumer_reads_pending_markers`
- `test_consumer_clear_pending`
- `test_consumer_dry_run`
- `test_consumer_skips_corrupt_markers`
- `test_consumer_push_queue_fallback`

### How It Works

```
EventLoop.capture() → Engram saved to SQLite
                     → PLURBridge.capture_to_plur() writes marker to plur_sync_pending.json
                     → Consumer reads markers
                     → Calls plur_learn (direct) OR writes to push queue (fallback)
                     → PostToolUse hook reads push queue → calls plur_learn
```

### PostToolUse Hook Integration

When the consumer writes to `plur_sync_push_pending.jsonl`, the Hermes Agent's
PostToolUse hook should read this file and call `plur_learn` for each entry.
The hook can detect this file and automatically process entries before ending
the session.

## Known Issues
- VectorStore: libtorchcodec fails to load → falls back to TF-IDF (fine for now)
- Most engrams have empty statements (Captured from terminal: {}) — real agent sessions will populate these

## Next Steps

### Priority 1: PostToolUse Hook for Push Queue
- Implement the hook that reads `plur_sync_push_pending.jsonl`
- Hook should call `plur_learn` for each entry in the queue
- Hook should remove processed entries from the queue
- This completes the end-to-end sync: capture → queue → PLUR

### Priority 2: Test with Real Agent Sessions
- Run capture during actual Hermes Agent sessions
- Verify engram quality and statement extraction
- Test BM25 search with real content

### Priority 3: Improve Statement Extraction
- Better terminal output parsing (filter commands, keep outputs)
- Context-aware extraction (tool name + output + user intent)
- Handle multi-line outputs, JSON responses, error messages

### Priority 4: Vector Search Fix
- Fix libtorchcodec issue or use alternative embedding model
- Enable semantic search for better recall

### Priority 5: Hermes Agent Skill
- Create SKILL.md for easy MCP server integration
- Document tool usage patterns
- Add example queries

### Priority 6: PLUR Sync
- Test bidirectional sync with actual PLUR engrams
- Verify deduplication and conflict resolution
- Test PostToolUse hook integration
