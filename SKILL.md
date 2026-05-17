---
name: neural-memory
description: "NeuralMemory — persistent agent memory with PLUR integration. Provides engram storage, hybrid search, priority decay, and PostToolUse capture hooks."
version: 1.0.0
author: Hermes Agent + NeuralMemory
license: MIT
platforms: [linux, macos, windows]
metadata:
  neural-memory:
    tags: [memory, engram, plur, neural, capture, search]
    homepage: https://github.com/NousResearch/neural-memory
---

# NeuralMemory

NeuralMemory is a persistent agent memory system that integrates with Hermes Agent. It provides:

- **PostToolUse capture** — automatically saves meaningful tool events as engrams
- **Hybrid search** — BM25 + vector search with RRF fusion
- **Priority decay** — automatic memory tier management
- **PLUR integration** — syncs with existing PLUR engram store
- **Web dashboard** — Streamlit-based browsing and management

## Quick Start

```bash
# Install (copy to skills dir + configure)
python setup.py --auto

# Start dashboard
streamlit run src/dashboard/app.py

# Or use via MCP server (auto-configured by setup.py)
```

## Configuration

Edit `config.yaml` to customize capture patterns:

```yaml
capture:
  enabled: true
  max_events_per_session: 100
  filter_patterns:
    - user_correction
    - debug_breakthrough
    - tool_discovery
    - user_preference
    - budget_constraint
    - file_operation
    - config_change
    - workflow_discovery
```

## Architecture

```
NeuralMemory/
├── hooks/
│   └── capture.py          # PostToolUse hook script
├── src/
│   ├── storage/            # SQLite engram store
│   ├── search/             # BM25 + vector search
│   ├── capture/            # Event extraction
│   ├── bridge/             # PLUR bridge
│   ├── mcp/                # MCP server
│   └── dashboard/          # Streamlit web UI
├── setup.py                # Installation script
├── config.yaml             # Filter patterns and storage config
└── SKILL.md                # This file
```

## How It Works

1. **Capture**: PostToolUse hook fires on every tool call
2. **Filter**: Only events matching filter patterns are captured
3. **Extract**: Statement, context, and metadata are extracted
4. **Store**: Engrams are saved to SQLite with PLUR-compatible format
5. **Search**: Hybrid search combines BM25 (keyword) and vector (semantic)
6. **Decay**: Priority decay automatically manages memory tiers

## Capture Patterns

| Pattern | Tools | Triggers |
|---------|-------|----------|
| `user_correction` | plur_learn, plur_forget, plur_promote, plur_feedback, memory, skill_manage, clarify | correct, no use, not Y, prefer, always, never, wrong, mistake, fixed |
| `debug_breakthrough` | terminal, execute_code, browser_console, session_search, search_files | fix, bug, error, timeout, root cause, traceback, exception, solved, resolved, worked, success |
| `tool_discovery` | browser_navigate, browser_snapshot, browser_click, browser_type, browser_press, skill_view, skills_list | page loaded, successfully, found, installed, available, registered, working |
| `user_preference` | plur_learn, plur_ingest, memory | prefers, wants, likes, dislikes, avoid, skip, prefer, always, never |
| `budget_constraint` | terminal, plur_learn, browser_navigate | budget, price, ₹, rupee, cost, cheap, expensive, free, paid, subscription |
| `file_operation` | write_file, patch, read_file, search_files, file | *(always matches — the path itself is the signal)* |
| `config_change` | write_file, patch, terminal | config, yaml, settings, setup, install, pip install, npm install, brew install |
| `workflow_discovery` | terminal, execute_code, browser_navigate, skill_view | workflow, pipeline, process, automate, script, build, deploy, test |

## Memory Tiers

- **Procedural**: How-to knowledge (code patterns, workflows)
- **Semantic**: Factual knowledge (concepts, definitions)
- **Episodic**: Event-based memories (sessions, interactions)

## API Reference

### Python API

```python
from src.storage.engrams import EngramStore
from src.search.hybrid import HybridSearch

# Store
store = EngramStore()
store.save(engram)

# Search
bm25 = BM25Index()
vector = VectorStore()
hybrid = HybridSearch(store, bm25, vector)
results = hybrid.search("user correction", limit=10)

# Decay
decay = PriorityDecay(store)
decay.apply_decay()
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `neural_memory_search` | Search engrams by query |
| `neural_memory_get` | Get engram by ID |
| `neural_memory_get_all` | List all engrams |
| `neural_memory_delete` | Delete engram by ID |
| `neural_memory_stats` | Get memory statistics |
| `neural_memory_tiers` | Get tier statistics |
| `neural_memory_apply_decay` | Apply priority decay |
| `neural_memory_trim_tiers` | Trim memory tiers |

## Installation for Community

### Option 1: Direct Install (Recommended)

```bash
# Clone or copy the project
mkdir -p ~/.hermes/skills/neural-memory
cd ~/.hermes/skills/neural-memory
# Copy all files from this repo here

# Install dependencies and configure
python setup.py --auto
```

### Option 2: Git Clone

```bash
git clone <repo-url> ~/.hermes/skills/neural-memory
cd ~/.hermes/skills/neural-memory
python setup.py --auto
```

### Option 3: Pip Install

```bash
pip install neural-memory
python -m neural_memory.setup --auto
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License — see LICENSE file for details.
