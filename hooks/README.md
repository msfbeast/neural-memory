# NeuralMemory Hooks

PostToolUse shell hooks for the NeuralMemory system. These scripts run on every tool call in Hermes Agent to capture events and sync engrams to PLUR.

## Hook Flow

```
Tool Call → Hermes sends JSON to stdin
    │
    ├─→ capture.py (timeout: 5s)
    │     ├─ Reads event from stdin
    │     ├─ Checks if "interesting" (correction, debug, error, tool discovery)
    │     ├─ If enabled: saves engram to SQLite store
    │     └─ Writes marker to pending markers file
    │
    └─→ plur_push.py (timeout: 10s)
          ├─ Reads push queue (plur_sync_push_pending.jsonl)
          ├─ Calls plur_learn for each entry
          └─ Removes processed entries from queue
```

## Hooks

### capture.py

Auto-captures "interesting" tool events and saves them to the engram store.

**Trigger:** Every tool call (via `hooks.post_tool_call` in config.yaml)

**How it works:**
1. Reads JSON event from stdin (Hermes sends this on every tool call)
2. Checks if the event matches interesting patterns:
   - User corrections ("no, use X not Y")
   - Debug/breakthrough moments
   - Error patterns (circular imports, missing modules, etc.)
   - Tool discovery (new MCP servers, tools, etc.)
3. If enabled and interesting: saves engram to SQLite store
4. Writes marker to pending markers file for PLUR sync

**Config:**
```yaml
hooks:
  post_tool_call:
    - command: "python3 ~/.hermes/skills/neural-memory/hooks/capture.py"
      timeout: 5
```

**Debug:** Set `NEURAL_MEMORY_DEBUG=1` to log all events to stderr.

### plur_push.py

Processes the PLUR push queue — engrams that couldn't be synced directly.

**Trigger:** Every tool call (via `hooks.post_tool_call` in config.yaml)

**How it works:**
1. Reads pending entries from `plur_sync_push_pending.jsonl`
2. For each entry, calls `plur_learn` via `hermes_tools`
3. Removes processed entries from the queue
4. Failed entries remain in the queue for retry on the next hook run

**When it runs:** Only when the consumer can't call `plur_learn` directly (e.g., running outside a Hermes session)

**Config:**
```yaml
hooks:
  post_tool_call:
    - command: "python3 ~/.hermes/skills/neural-memory/hooks/plur_push.py"
      timeout: 10
```

**Debug:** Set `NEURAL_MEMORY_DEBUG=1` to log all events to stderr.

## Push Queue Format

The push queue file (`plur_sync_push_pending.jsonl`) contains one JSON object per line:

```json
{
  "action": "plur_learn",
  "engram_id": "engram-uuid",
  "statement": "The knowledge assertion",
  "scope": "global",
  "type": "behavioral",
  "domain": "neural_memory",
  "tags": ["neural_memory", "plur_sync"],
  "rationale": "why this matters",
  "visibility": "private",
  "source": "neural_memory_consumer",
  "queued_at": "2026-05-17T21:59:00+00:00"
}
```

## Testing

Run the test suite:
```bash
cd /path/to/neural-memory
python -m pytest tests/test_plur_push_hook.py -v
python -m pytest tests/ -v  # Full suite
```

## Pitfalls

1. **Hooks must be fast** — They run on every tool call. If a hook takes too long, it blocks the agent. Use timeouts (5s for capture.py, 10s for plur_push.py).

2. **Hooks exit silently when nothing to do** — Both hooks exit with code 0 when there's no work. This prevents unnecessary overhead.

3. **plur_push.py requires hermes_tools** — The `plur_learn` function is only available when running inside a Hermes session. If not available, entries remain in the queue for the next hook run.

4. **Queue file is atomic** — The push queue is read and written atomically. If multiple hooks run simultaneously, the last write wins (but entries are deduplicated by the consumer).

5. **Debug mode logs to stderr** — Set `NEURAL_MEMORY_DEBUG=1` to see all hook events. This is useful for troubleshooting but can be noisy in production.
