# NeuralMemory

Automatic engram capture for AI agents. Watches tool calls and saves meaningful events as searchable memories.

## What it does

Every time an AI agent uses a tool (terminal, browser, file ops, etc.), NeuralMemory:
1. **Filters** the event against configurable patterns
2. **Extracts** a human-readable statement from the tool + input + result
3. **Deduplicates** against existing memories
4. **Saves** to a searchable store with hybrid BM25 + vector search

## Features

- **PostToolUse capture** — automatic memory capture from tool usage
- **Hybrid search** — BM25 (keyword) + vector (semantic) search with RRF fusion
- **Priority decay** — automatic memory tier management
- **PLUR integration** — syncs with existing PLUR engram store
- **Web dashboard** — Streamlit-based browsing and management
- **MCP server** — query memories via MCP protocol

## Quick Start

```bash
# Install
python setup.py --auto

# Start dashboard
streamlit run src/dashboard/app.py

# Or use via MCP server (auto-configured)
```

## Architecture

```
AI Agent → post_tool_call hook → capture.py → EngramStore → BM25 + Vector index
                                        ↓
                                 MCP Server (query API)
                                        ↓
                                 Streamlit Dashboard
```

## Installation

### Option 1: Direct Install (Recommended)

```bash
# Clone or copy the project
mkdir -p ~/.hermes/skills/neural-memory
cd ~/.hermes/skills/neural-memory
# Copy all files from this repo

# Install dependencies and configure
python setup.py --auto
```

### Option 2: Git Clone

```bash
git clone https://github.com/NousResearch/neural-memory.git ~/.hermes/skills/neural-memory
cd ~/.hermes/skills/neural-memory
python setup.py --auto
```

### Option 3: Shell Script

```bash
git clone https://github.com/NousResearch/neural-memory.git ~/.hermes/skills/neural-memory
cd ~/.hermes/skills/neural-memory
chmod +x install.sh
./install.sh --auto
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

## Filter Patterns

| Pattern | Tools | Description |
|---------|-------|-------------|
| `user_correction` | plur_learn, plur_forget, memory, skill_manage, clarify | User corrected the agent |
| `debug_breakthrough` | terminal, execute_code, browser_console, session_search | Debug session with a solution |
| `tool_discovery` | browser_navigate, browser_snapshot, skill_view, skills_list | Tool discovery or setup |
| `user_preference` | plur_learn, plur_ingest, memory | User preference or habit |
| `budget_constraint` | terminal, plur_learn, browser_navigate | Budget or pricing constraint |
| `file_operation` | write_file, patch, read_file, search_files | Important file operations |
| `config_change` | write_file, patch, terminal | Config/setup changes |
| `workflow_discovery` | terminal, execute_code, browser_navigate | New workflow discovered |

## API Reference

### Python API

```python
from src.storage.engrams import EngramStore
from src.search.hybrid import HybridSearch

# Store
store = EngramStore()
store.save(engram)

# Search
hybrid = HybridSearch(store)
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

## Testing

Test the hook with a sample event:

```bash
echo '{
  "hook_event_name": "post_tool_call",
  "tool_name": "terminal",
  "tool_input": {"command": "cat config.yaml"},
  "session_id": "test-123",
  "cwd": "/Users/msfbeast",
  "extra": {"result": "# config\nkey: value"}
}' | python3 hooks/capture.py
```

## File Layout

```
neural-memory/
├── README.md              # This file
├── config.yaml            # Filter patterns and storage config
├── hooks/
│   └── capture.py         # PostToolUse hook (main entry point)
├── src/
│   ├── mcp/
│   │   ├── run.py         # MCP server entry point
│   │   └── server.py      # MCP tool implementations
│   ├── storage/
│   │   ├── engrams.py     # SQLite engram store
│   │   └── vector.py      # Vector store
│   ├── capture/
│   │   ├── extractor.py   # Statement extraction
│   │   └── filters.py     # Filter definitions
│   └── dashboard/
│       └── app.py         # Streamlit UI
├── tests/
│   └── test_capture.py    # Hook unit tests
├── setup.py               # Installation script
├── install.sh             # Shell installer
├── requirements.txt       # Python dependencies
└── SKILL.md               # Skill metadata
```

## License

MIT License
