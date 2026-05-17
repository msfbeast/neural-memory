# NeuralMemory — Fusion Architecture

> PLUR's structured engrams + agentmemory's auto-capture = zero-effort, high-signal memory.

## Problem

PLUR requires manual `plur_learn` — high signal but easy to forget.
agentmemory auto-captures everything — zero effort but noisy.

## Solution

**Auto-capture → PLUR engrams.** Every tool use auto-converts to a structured engram.
No noise. No manual calls. Just memory that works.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Capture Layer                        │
│  (agentmemory-style hooks, PLUR-format output)          │
│                                                         │
│  PostToolUse → AutoExtract → EngramBuilder → PLUR       │
│  SessionStart → ProjectProfile → PLUR                   │
│  SessionEnd → SessionSummary → PLUR                     │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                   Storage Layer                         │
│  (PLUR engrams + BM25 index + vector index)             │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Engrams  │  │  BM25    │  │   Vector (local)     │  │
│  │ (SQLite) │  │  (whoosh)│  │   (sentence-transformers) │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│                                                         │
│  4-Tier Memory:                                         │
│  Working → Episodic → Semantic → Procedural             │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                   Search Layer                          │
│  (Hybrid: BM25 + Vector + Graph + PLUR recall)          │
│                                                         │
│  RRF Fusion:                                            │
│  score = 0.4*BM25 + 0.4*Vector + 0.2*Graph             │
│                                                         │
│  Token budget: 2000 tokens max injection                │
│  Decay: Ebbinghaus curve on all tiers                   │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                   Output Layer                          │
│  (MCP tools + REST API + Web viewer)                    │
│                                                         │
│  MCP: memory_capture, memory_search, memory_recall      │
│       memory_forget, memory_promote, memory_stats       │
│  REST: /capture, /search, /recall, /forget, /stats      │
│  Viewer: localhost:3113 (real-time memory browser)      │
└─────────────────────────────────────────────────────────┘
```

## 4-Tier Memory Model

| Tier | Source | PLUR Type | Decay |
|------|--------|-----------|-------|
| Working | Raw tool events | None (temporary) | 1 hour |
| Episodic | Session summaries | behavioral | 7 days |
| Semantic | Extracted facts | terminological, behavioral | 30 days |
| Procedural | Workflows, patterns | procedural, architectural | 90 days |

## Auto-Capture Rules

Not every tool call becomes an engram. Filter:

- **SAVE** (high signal):
  - User corrections ("use X not Y")
  - Debugging breakthroughs
  - New workflow discoveries
  - Architecture decisions
  - API quirks / gotchas
  - User preferences
  - Budget constraints
  - Project conventions

- **IGNORE** (noise):
  - Routine file reads
  - Standard terminal commands
  - Git operations
  - Cron job listings
  - Simple lookups

## Implementation Plan

### Phase 1: Core (Week 1)
- Auto-capture event loop (Python, no iii-engine)
- BM25 search (whoosh library)
- Local vector embeddings (sentence-transformers)
- PLUR engram format compatibility
- Basic MCP server

### Phase 2: Intelligence (Week 2)
- Auto-extraction rules (what to save vs ignore)
- 4-tier consolidation pipeline
- Knowledge graph (networkx)
- Memory decay (Ebbinghaus)
- RRF fusion search

### Phase 3: UX (Week 3)
- Web viewer (Streamlit, like agentmemory)
- REST API
- Team memory (namespace support)
- Privacy filtering (auto-strip secrets)

### Phase 4: Integration (Week 4)
- PLUR compatibility layer (read/write PLUR engrams)
- agentmemory bridge (optional, for hook reuse)
- Migration tool (PLUR → NeuralMemory)
- Documentation

## Dependencies

```
python>=3.11
whoosh           # BM25 search
sentence-transformers  # local embeddings
networkx         # knowledge graph
streamlit        # web viewer
fastapi          # REST API
uvicorn          # ASGI server
```

**No Node.js. No iii-engine. No external API keys.**

## Key Differences from PLUR

1. **Auto-capture**: No manual `plur_learn` — everything is automatic
2. **BM25 search**: Exact keyword matching + semantic search
3. **4-tier consolidation**: Memories evolve over time
4. **Knowledge graph**: Entity relationships, not just meta-engrams
5. **Privacy**: Auto-strips API keys, secrets, tokens
6. **Viewer**: Real-time web UI
7. **Team**: Shared memory across multiple agents

## Phases

### ✅ Phase 1: Core (DONE — 2026-05-16)
- Config loader (YAML + defaults)
- Capture event loop (PostToolUse, SessionStart, SessionEnd)
- Filter system (save/ignore rules, confidence scoring)
- Engram extractor (auto-generate PLUR-compatible engrams)
- SQLite engram store (PLUR-compatible schema)
- BM25 search (Whoosh)
- Vector store (sentence-transformers + TF-IDF fallback)
- MCP server (stdio transport)
- CLI interface

**Demo results**: 6/6 sample events captured, BM25 search returns results, all storage backends initialized.

### 📋 Phase 2: Search & Recall
- Hybrid search (BM25 + vector RRF fusion)
- Recall tool (top-K with reranking)
- Session context builder (auto-summarize recent engrams)
- Similarity search (cosine similarity)
- Category-aware search (filter by type)

### 📋 Phase 3: Consolidation
- Working memory (raw engrams, last 24h)
- Episodic consolidation (group by session)
- Semantic abstraction (extract principles)
- Procedural generalization (turn into reusable patterns)
- Ebbinghaus decay (forget stale memories)

### 📋 Phase 4: Integration
- PLUR bridge (read/write PLUR engrams)
- Auto-discovery (find PLUR engrams via NeuralMemory search)
- Feedback loop (PLUR feedback → NeuralMemory ranking)
- Migration tool (PLUR → NeuralMemory)

### 📋 Phase 5: Polish
- REST API (optional)
- Web viewer (optional)
- Performance optimization
- Documentation
- Tests

## Key Differences from agentmemory

1. **No iii-engine**: Pure Python, no separate binary
2. **No external API keys**: Local embeddings only
3. **PLUR-compatible**: Can read/write PLUR engrams directly
4. **Focused**: No 104 REST endpoints, just what we need
5. **Smaller**: ~5K lines vs ~31K lines

## Migration Path

```
Day 1: Install NeuralMemory alongside PLUR
Day 3: Run both, compare results
Day 7: Disable PLUR, use NeuralMemory only
Day 14: Migrate PLUR engrams → NeuralMemory format
Day 30: Remove PLUR, complete migration
```

## File Structure

```
neural-memory/
├── src/
│   ├── capture/          # Auto-capture event loop
│   │   ├── event_loop.py
│   │   ├── filters.py    # Save vs ignore rules
│   │   └── extractor.py  # Auto-extract engrams from events
│   ├── storage/          # Storage backends
│   │   ├── engrams.py    # PLUR-compatible engram store
│   │   ├── bm25.py       # Whoosh BM25 index
│   │   ├── vector.py     # Local vector index
│   │   └── graph.py      # Knowledge graph (networkx)
│   ├── search/           # Hybrid search
│   │   ├── hybrid.py     # RRF fusion
│   │   └── reranker.py   # LLM reranker (optional)
│   ├── consolidation/    # 4-tier pipeline
│   │   ├── working.py    # Raw → episodic
│   │   ├── episodic.py   # Episodic → semantic
│   │   ├── semantic.py   # Semantic → procedural
│   │   └── decay.py      # Ebbinghaus decay
│   ├── mcp/              # MCP server
│   │   ├── server.py
│   │   └── tools.py      # MCP tool definitions
│   ├── api/              # REST API
│   │   ├── routes.py
│   │   └── auth.py
│   └── viewer/           # Web viewer
│       └── app.py        # Streamlit app
├── tests/
├── config.yaml           # Configuration
├── requirements.txt
└── README.md
```
