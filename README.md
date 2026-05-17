# NeuralMemory

Automatic engram capture for Hermes Agent. Watches tool calls and saves meaningful events as searchable engrams.

## What it does

Every time Hermes Agent uses a tool (terminal, browser, file ops, etc.), the hook:
1. **Filters** the event against configurable patterns
2. **Extracts** a human-readable statement from the tool + input + result
3. **Deduplicates** against existing engrams
4. **Saves** to the PLUR-compatible engram store

## Architecture

```
Hermes Agent → post_tool_call hook → capture.py → EngramStore → BM25 + Vector index
                                              ↓
                                       MCP Server (query API)
                                              ↓
                                       Streamlit Dashboard
```

## Components

- **hooks/capture.py** — Shell hook that runs on every post_tool_call
- **src/mcp/server.py** — MCP server exposing memory tools
- **src/storage/engrams.py** — SQLite engram storage
- **src/storage/vector.py** — Vector store (sentence-transformers)
- **src/capture/extractor.py** — Statement extraction logic
- **src/dashboard/app.py** — Streamlit UI for browsing/searching engrams
- **config.yaml** — Filter patterns, storage paths, search weights

## Installation

### 1. Install the skill

```bash
cp -r /path/to/neural-memory ~/.hermes/skills/neural-memory
```

Or clone from git:

```bash
git clone <repo-url> ~/.hermes/skills/neural-memory
```

### 2. Run setup

```bash
cd ~/.hermes/skills/neural-memory
python setup.py --auto
```

This will:
- Install Python dependencies (streamlit, sentence-transformers, rank-bm25, pyyaml)
- Register the PostToolUse hook in `~/.hermes/config.yaml`
- Configure the MCP server in `~/.hermes/config.yaml`
- Copy the skill to `~/.hermes/skills/neural-memory`

### 3. Accept the hook

On first run, Hermes Agent will prompt for consent. Approve it, or set:

```yaml
hooks_auto_accept: true
```

### 4. (Optional) Start the dashboard

```bash
streamlit run src/dashboard/app.py
```

Dashboard runs at `http://localhost:8507`

## Filter Patterns

Events are only captured if they match a filter pattern. Each pattern has:
- **name** — Pattern identifier
- **tools** — Which tools trigger this pattern
- **patterns** — Keywords to match in the event content

### Built-in patterns

| Pattern | Tools | Keywords | Description |
|---------|-------|----------|-------------|
| user_correction | plur_learn, plur_forget, plur_promote, plur_feedback, memory, skill_manage, clarify | correct, no use, not Y, prefer, always, never, wrong, mistake, fixed | User corrected the agent |
| debug_breakthrough | terminal, execute_code, browser_console, session_search, search_files | fix, bug, error, timeout, root cause, traceback, exception, solved, resolved, worked, success | Debug session with a solution |
| tool_discovery | browser_navigate, browser_snapshot, browser_click, browser_type, browser_press, skill_view, skills_list | page loaded, successfully, found, installed, available, registered, working | Tool discovery or setup |
| user_preference | plur_learn, plur_ingest, memory | prefers, wants, likes, dislikes, avoid, skip, prefer, always, never | User preference or habit |
| budget_constraint | terminal, plur_learn, browser_navigate | budget, price, ₹, rupee, cost, cheap, expensive, free, paid, subscription | Budget or pricing constraint |
| file_operation | write_file, patch, read_file, search_files, file | *(none — always matches)* | Important file operations |
| config_change | write_file, patch, terminal | config, yaml, settings, setup, install, pip install, npm install, brew install | Config/setup changes |
| workflow_discovery | terminal, execute_code, browser_navigate, skill_view | workflow, pipeline, process, automate, script, build, deploy, test | New workflow discovered |

### Customizing patterns

Edit `config.yaml`:

```yaml
capture:
  filter_patterns:
    - user_correction
    - debug_breakthrough
    # Remove patterns you don't want
    # - tool_discovery
```

Or add custom patterns in `capture.py`'s `FILTER_PATTERNS` list.

## Debug Mode

Set `NEURAL_MEMORY_DEBUG=1` to log all events to stderr:

```bash
# Test a single event
echo '{"tool_name":"terminal","tool_input":{"command":"ls"},"extra":{}}' | \
  NEURAL_MEMORY_DEBUG=1 python3 ~/.hermes/skills/neural-memory/hooks/capture.py
```

## Statement Extraction

The hook builds rich statements by combining:
- **Tool name** — What was called
- **Tool input** — What was passed to it
- **Result/output** — What came back

Examples:
- `Terminal: cat file.py → #!/usr/bin/env python3` (command + first lines of output)
- `Write: /path/to/file.py` (file path)
- `Patch: /path/to/file.py\n- old line\n+ new line` (diff preview)
- `plur_learn: User correction on plur_learn: Project uses pytest with xdist` (direct statement)

## Troubleshooting

### Hook not firing

1. Check the hook is registered: `hermes hooks list`
2. Check the allowlist: `~/.hermes/shell-hooks-allowlist.json`
3. Check Hermes logs for errors: `~/.hermes/logs/`

### No engrams being saved

1. Enable debug mode: `NEURAL_MEMORY_DEBUG=1`
2. Check stderr output for filter mismatches
3. Verify the filter patterns include your tool: check `FILTER_PATTERNS` in `capture.py`
4. Check the EngramStore path exists: `~/.plur/neural_memory/`

### Duplicate engrams

The hook uses content hashing for deduplication. If you still see duplicates:
1. Check `check_dedup()` in `capture.py` — it searches for similar statements
2. The similarity threshold is 85% word overlap
3. You can increase it by changing `0.85` to a higher value

### MCP server not responding

1. Check the server is running: `python3 src/mcp/run.py`
2. Check for errors in stderr
3. Verify dependencies: `pip install sentence-transformers pyyaml`

### Dashboard not loading

1. Check Streamlit is installed: `pip install streamlit`
2. Run: `streamlit run src/dashboard/app.py`
3. Check the database exists: `~/.plur/neural_memory/engrams.db`

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
│   ├── marketplace/
│   │   ├── redactor.py    # Sensitive data redaction
│   │   ├── cards.py       # Shareable memory/pack cards
│   │   ├── packs.py       # Pack management
│   │   └── client.py      # Marketplace client
│   └── dashboard/
│       └── app.py         # Streamlit UI (with Marketplace tab)
├── tests/
│   └── test_capture.py    # Hook unit tests
├── setup.py               # Installation script
├── requirements.txt       # Python dependencies
└── SKILL.md               # Skill metadata
```

## Testing

Test the hook with a sample event:

```bash
echo '{
  "hook_event_name": "post_tool_call",
  "tool_name": "terminal",
  "tool_input": {"command": "cat config.yaml"},
  "session_id": "test-123",
  "cwd": "/Users/msfbeast",
  "extra": {"result": "# config\\nkey: value"}
}' | python3 hooks/capture.py
```

Check the engram was saved:

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from storage.engrams import EngramStore
store = EngramStore()
stats = store.get_stats()
print(f'Total engrams: {stats[\"total\"]}')
"
```

## Marketplace

Share your captured knowledge with the community. Browse and install packs created by others.

### Privacy-First Design

- **All memories are private by default** — nothing is shared unless you explicitly opt in
- **Auto-redaction** — sensitive data (API keys, paths, emails, tokens) is automatically stripped before sharing
- **One-click unshare** — remove any memory from the marketplace at any time

### Sharing a Memory

Via MCP tool:
```json
{"jsonrpc": "2.0", "id": 1, "method": "memory_share", "params": {
  "engram_id": "NM-20260516-abc123",
  "title": "My custom title",
  "author": "myusername",
  "tags": "python, debugging, best-practices"
}}
```

Via Dashboard: Go to **Marketplace → Share Memory**, paste the engram ID, and click "Share".

### Redaction Preview

The dashboard includes a redaction preview tool. Paste any text to see how sensitive data would be redacted before sharing.

### Browsing Packs

Via MCP tool:
```json
{"jsonrpc": "2.0", "id": 1, "method": "memory_browse_packs", "params": {
  "query": "python debugging",
  "tags": "python, best-practices"
}}
```

Via Dashboard: Go to **Marketplace → Browse Packs**, search by query or tags.

### Downloading a Pack

```json
{"jsonrpc": "2.0", "id": 1, "method": "memory_download_pack", "params": {
  "pack_id": "pack-20260516-abc123"
}}
```

### Managing Your Shared Memories

```json
// List what you've shared
{"jsonrpc": "2.0", "id": 1, "method": "memory_list_shared", "params": {}}

// Unshare a memory
{"jsonrpc": "2.0", "id": 1, "method": "memory_unshare", "params": {
  "engram_id": "NM-20260516-abc123"
}}

// Create a pack from your memories
{"jsonrpc": "2.0", "id": 1, "method": "memory_create_pack", "params": {
  "name": "Python Debugging Patterns",
  "description": "Common debugging patterns I've discovered",
  "card_ids": "NM-20260516-abc1, NM-20260516-def2, NM-20260516-ghi3",
  "tags": "python, debugging",
  "author": "myusername"
}}
```

### Sensitive Data Patterns

The redactor automatically detects and redacts:
- API keys and tokens (GitHub, AWS, JWT, generic)
- Absolute file paths (`/Users/...`, `/home/...`)
- Email addresses
- Phone numbers
- IP addresses
- Credit card numbers

### Architecture

```
┌─────────────────────────────────────────────────┐
│                  Marketplace                    │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  Share   │  │  Browse  │  │   My Shared  │  │
│  │  Memory  │  │  Packs   │  │   Manage     │  │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│       │              │               │           │
│       ▼              ▼               ▼           │
│  ┌────────────────────────────────────────────┐  │
│  │           Redaction Engine                 │  │
│  │  (API keys, paths, emails, tokens)         │  │
│  └────────────────────────────────────────────┘  │
│       │              │               │           │
│       ▼              ▼               ▼           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  Pack    │  │  Pack    │  │  Memory      │  │
│  │  Store   │  │  Store   │  │  Cards       │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────┘
```
