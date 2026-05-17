#!/usr/bin/env python3
"""NeuralMemory CLI — Phase 4: Lifecycle Management.

Usage:
    python -m src.main capture <event_json>     # Capture an event
    python -m src.main search <query>           # Search memories (BM25)
    python -m src.main search-hybrid <query>    # Hybrid BM25+vector search
    python -m src.main similar <statement>      # Find similar engrams
    python -m src.main context [hours]          # Build context summary
    python -m src.main recall [category]        # Recall by category
    python -m src.main dedup                    # Find and merge duplicates
    python -m src.main decay                    # Apply priority decay
    python -m src.main forget <id>              # Forget an engram
    python -m src.main forget-query <query>     # Forget by search query
    python -m src.main tiers                    # Show tier statistics
    python -m src.main plur-sync                # Sync with PLUR
    python -m src.main plur-status              # Show PLUR sync status
    python -m src.main stats                    # Show stats
    python -m src.main list [limit] [offset]    # List engrams
    python -m src.main delete <id>              # Delete engram
    python -m src.main mcp                      # Start MCP server
    python -m src.main demo                     # Run demo with sample data
"""

import json
import os
import sys
import argparse

from src.capture.event_loop import EventLoop
from src.capture.extractor import Engram
from src.config import config
from src.search.hybrid import HybridSearch
from src.search.similarity import SimilaritySearch
from src.search.context import ContextBuilder
from src.storage.engrams import EngramStore
from src.storage.bm25 import BM25Index
from src.storage.vector import VectorStore


# ── Command implementations (all defined before main) ──────────────────────

def cmd_capture(args: argparse.Namespace) -> None:
    """Capture a single event."""
    loop = EventLoop()
    try:
        event = json.loads(args.event)
        engram = loop.capture(event)
        if engram:
            print(f"[OK] Saved engram: {engram.id}")
            print(f"  Type: {engram.type}")
            print(f"  Category: {engram.category}")
            print(f"  Confidence: {engram.confidence:.2f}")
            print(f"  Statement: {engram.statement[:200]}")
        else:
            print("[SKIP] Event filtered out or extraction failed")
    finally:
        loop.close()


def cmd_search(args: argparse.Namespace) -> None:
    """Search memories."""
    loop = EventLoop()
    try:
        results = loop.search(args.query, top_k=args.top_k)
        if not results:
            print("[No results]")
            return
        print(f"[{len(results)} results for: {args.query}]\n")
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r.get('score', 0):.4f}] {r['statement'][:150]}")
            print(f"     Type: {r.get('type', '')} | Category: {r.get('category', '')}")
    finally:
        loop.close()


def cmd_search_hybrid(args: argparse.Namespace) -> None:
    """Hybrid BM25 + vector search."""
    loop = EventLoop()
    try:
        hybrid = HybridSearch(loop._store, loop._bm25, loop._vector)
        results = hybrid.search(args.query, limit=args.top_k)
        if not results:
            print("[No results]")
            return
        print(f"[{len(results)} results for: {args.query}]\n")
        for i, r in enumerate(results, 1):
            bm25_str = f"{r.bm25_score:.4f}" if r.bm25_score > 0 else "N/A"
            vec_str = f"{r.vector_score:.4f}" if r.vector_score > 0 else "N/A"
            print(f"  {i}. [{r.score:.4f}] {r.statement_short}")
            print(f"     BM25: {bm25_str} | Vector: {vec_str} | Cat: {r.category}")
    finally:
        loop.close()


def cmd_similar(args: argparse.Namespace) -> None:
    """Find similar engrams."""
    loop = EventLoop()
    try:
        sim = SimilaritySearch(loop._store, loop._vector, loop._bm25)
        results = sim.find_similar(args.statement, limit=args.top_k)
        if not results:
            print("[No similar engrams found]")
            return
        print(f"[{len(results)} similar to: {args.statement[:80]}]\n")
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['score']:.4f}] {r['statement'][:120]}")
            print(f"     Cat: {r.get('category', '')}")
    finally:
        loop.close()


def cmd_context(args: argparse.Namespace) -> None:
    """Build context summary from recent engrams."""
    loop = EventLoop()
    try:
        hours = args.hours if hasattr(args, 'hours') and args.hours else 24
        ctx = ContextBuilder(loop._store)
        summary = ctx.build_context(hours=hours)
        print(summary)
    finally:
        loop.close()


def cmd_recall(args: argparse.Namespace) -> None:
    """Recall engrams by category/type/domain."""
    loop = EventLoop()
    try:
        results = loop._store.get_all(limit=args.limit)
        if args.category:
            results = loop._store.search_by_category(args.category, args.limit)
        elif args.type:
            results = loop._store.search_by_type(args.type, args.limit)
        elif args.domain:
            results = loop._store.search_by_domain(args.domain, args.limit)

        if not results:
            print("[No results]")
            return
        print(f"[{len(results)} results]\n")
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r.id}] {r.statement[:150]}")
            print(f"     Type: {r.type} | Category: {r.category}")
    finally:
        loop.close()


def cmd_stats(args: argparse.Namespace) -> None:
    """Show memory system statistics."""
    loop = EventLoop()
    try:
        stats = loop.get_stats()
        print("=== NeuralMemory Stats ===\n")
        print(f"Enabled: {stats['enabled']}")
        print(f"Session count: {stats['session_count']}")
        print(f"Store stats: {json.dumps(stats['store_stats'], indent=2)}")
        print(f"BM25 indexed: {stats['bm25_count']}")
        print(f"Vector store: {json.dumps(stats['vector_stats'], indent=2)}")
    finally:
        loop.close()


def cmd_list(args: argparse.Namespace) -> None:
    """List all engrams."""
    loop = EventLoop()
    try:
        engrams = loop._store.get_all(limit=args.limit, offset=args.offset)
        total = loop._store.count()
        print(f"[{len(engrams)} of {total} total]\n")
        for i, e in enumerate(engrams, 1):
            print(f"  {i}. [{e.id}] {e.statement[:120]}")
            print(f"     Type: {e.type} | Cat: {e.category} | Conf: {e.confidence:.2f}")
    finally:
        loop.close()


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete an engram."""
    loop = EventLoop()
    try:
        deleted = loop._store.delete(args.id)
        if deleted:
            loop._bm25.delete(args.id)
            print(f"[OK] Deleted: {args.id}")
        else:
            print(f"[NOT FOUND] {args.id}")
    finally:
        loop.close()


def cmd_mcp(args: argparse.Namespace) -> None:
    """Start MCP server."""
    from src.mcp.server import main as mcp_main
    mcp_main()


def cmd_demo(args: argparse.Namespace) -> None:
    """Run demo with sample events."""
    print("=== NeuralMemory Demo ===\n")

    # Use temp DB and temp BM25 index for demo (prevents leaks between runs)
    import tempfile
    import shutil
    tmpdb = tempfile.mktemp(suffix=".db")
    tmpbm25 = tempfile.mkdtemp(prefix="nm_bm25_demo_")
    old_db = config._data["storage"]["engrams_db"]
    old_bm25 = config._data["storage"]["bm25_index"]
    config._data["storage"]["engrams_db"] = tmpdb
    config._data["storage"]["bm25_index"] = tmpbm25

    loop = EventLoop()

    # Sample events that should be captured
    sample_events = [
        {
            "tool_name": "plur_learn",
            "user_message": "no, use X not Y",
            "output": "Saved engram successfully",
        },
        {
            "tool_name": "terminal",
            "output": "git commit -m 'fix bug'",
            "error": "",
        },
        {
            "tool_name": "browser_navigate",
            "user_message": "found a new tool called playwright",
            "output": "Page loaded successfully",
        },
        {
            "tool_name": "terminal",
            "output": "ls -la",
            "error": "",
        },
        {
            "tool_name": "debug",
            "output": "root cause traced to timeout in API call",
            "error": "ConnectionError: timeout",
        },
        {
            "tool_name": "plur_learn",
            "user_message": "user prefers concise responses",
            "output": "Memory saved",
        },
    ]

    print("Processing sample events...\n")
    captured = 0
    skipped = 0

    for event in sample_events:
        engram = loop.capture(event)
        if engram:
            captured += 1
            print(f"  [SAVED] {event['tool_name']}: {engram.statement[:80]}")
        else:
            skipped += 1
            print(f"  [SKIP]  {event['tool_name']}: filtered out")

    print(f"\nCaptured: {captured}, Skipped: {skipped}")

    # Demo BM25 search
    print("\n--- BM25 Search Demo ---")
    results = loop.search("debug timeout", top_k=5)
    print(f"Search 'debug timeout': {len(results)} results")
    for r in results:
        print(f"  [{r.get('score', 0):.4f}] {r['statement'][:100]}")

    # Demo hybrid search
    print("\n--- Hybrid Search Demo ---")
    hybrid = HybridSearch(loop._store, loop._bm25, loop._vector)
    hybrid_results = hybrid.search("debug timeout", limit=5)
    print(f"Hybrid 'debug timeout': {len(hybrid_results)} results")
    for r in hybrid_results:
        print(f"  [{r.score:.4f}] {r.statement_short}")
        print(f"     BM25: {r.bm25_score:.4f} | Vector: {r.vector_score:.4f}")

    # Demo similarity search
    print("\n--- Similarity Search Demo ---")
    sim = SimilaritySearch(loop._store, loop._vector, loop._bm25)
    sim_results = sim.find_similar("user prefers concise responses", limit=3)
    print(f"Similar to 'user prefers concise': {len(sim_results)} results")
    for r in sim_results:
        print(f"  [{r['score']:.4f}] {r['statement'][:100]}")

    # Demo context builder
    print("\n--- Context Builder Demo ---")
    ctx = ContextBuilder(loop._store)
    summary = ctx.build_context(hours=24)
    print(summary)

    # Demo stats
    print("\n--- Stats ---")
    stats = loop.get_stats()
    print(f"Total engrams: {stats['store_stats']['total']}")
    print(f"Types: {stats['store_stats']['by_type']}")
    print(f"Categories: {stats['store_stats']['by_category']}")

    loop.close()

    # Cleanup
    config._data["storage"]["engrams_db"] = old_db
    config._data["storage"]["bm25_index"] = old_bm25
    try:
        os.unlink(tmpdb)
    except OSError:
        pass
    try:
        shutil.rmtree(tmpbm25, ignore_errors=True)
    except OSError:
        pass

    print("\n[Demo complete]")


def cmd_plur_sync(args: argparse.Namespace) -> None:
    """Sync with PLUR: load engrams and show sync status."""
    from src.bridge.plur import PLURBridge

    bridge = PLURBridge()

    # Override direction if specified
    if hasattr(args, 'direction') and args.direction:
        bridge._sync_direction = args.direction

    bridge_config = bridge.get_sync_config()
    print("=== PLUR Sync Status ===\n")
    print(f"Enabled: {bridge_config['enabled']}")
    print(f"Sync enabled: {bridge_config['sync_enabled']}")
    print(f"Direction: {bridge_config['sync_direction']}")
    print(f"PLUR tools tracked: {', '.join(bridge_config['plur_tools'][:5])}...")

    # Load PLUR engrams
    print(f"\nLoading PLUR engrams into NeuralMemory index...")
    loaded = bridge.load_plur_engrams(limit=100)
    print(f"Loaded {len(loaded)} engrams from PLUR")

    # Show sync direction summary
    if bridge_config['sync_direction'] in ('both', 'capture_only'):
        print("Capture → PLUR: enabled (new engrams synced automatically)")
    else:
        print("Capture → PLUR: disabled")

    if bridge_config['sync_direction'] in ('both', 'recall_only'):
        print("PLUR → Capture: enabled")
    else:
        print("PLUR → Capture: disabled")


def cmd_plur_status(args: argparse.Namespace) -> None:
    """Show PLUR sync status without loading."""
    from src.bridge.plur import PLURBridge

    bridge = PLURBridge()
    bridge_config = bridge.get_sync_config()

    print("=== PLUR Sync Status ===\n")
    print(f"Enabled: {bridge_config['enabled']}")
    print(f"Sync enabled: {bridge_config['sync_enabled']}")
    print(f"Direction: {bridge_config['sync_direction']}")
    print(f"\nTracked PLUR tools ({len(bridge_config['plur_tools'])}):")
    for tool in bridge_config['plur_tools']:
        print(f"  - {tool}")


def cmd_plur_push(args: argparse.Namespace) -> None:
    """Push pending engrams from NeuralMemory to PLUR.

    Reads plur_sync_pending.json markers and calls plur_learn
    to persist them to the real PLUR store.
    """
    from src.bridge.consumer import PLURConsumer

    consumer = PLURConsumer()
    status = consumer.get_status()

    print("=== PLUR Push (NeuralMemory → PLUR) ===\n")
    print(f"Pending markers: {status['pending_count']}")
    print(f"Marker file: {status['marker_path']}")
    print()

    if status['pending_count'] == 0:
        print("Nothing to push. All markers processed.")
        return

    # Show what's pending (dry run first)
    print("Pending engrams:")
    markers = consumer.get_pending_markers()
    for i, m in enumerate(markers, 1):
        engram_id = m.get("nm_id", m.get("engram_id", "?"))[:16]
        statement = m.get("statement", "")[:80]
        scope = m.get("scope", "global")
        print(f"  {i}. [{engram_id}] scope={scope}")
        print(f"     {statement}...")
    print()

    if args.dry_run:
        print("[DRY RUN] No changes made.")
        return

    # Process all pending markers
    print("Processing markers...")
    results = consumer.process_all()

    # Summary
    success = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    print(f"\n=== Push Complete ===")
    print(f"  Success: {success}")
    print(f"  Failed:  {failed}")
    if failed > 0:
        print(f"\nFailed engrams remain in {status['marker_path']} for retry.")
        print("Tip: Run again later — failed markers may succeed on retry.")


def cmd_plur_clear(args: argparse.Namespace) -> None:
    """Clear pending PLUR sync markers."""
    from src.bridge.consumer import PLURConsumer

    consumer = PLURConsumer()
    count = consumer.clear_pending()
    print(f"Cleared {count} pending PLUR sync markers.")


def cmd_dedup(args: argparse.Namespace) -> None:
    """Find and merge duplicate engrams."""
    from src.storage.merging import EngramMerger

    store = EngramStore()
    vector = VectorStore()
    bm25 = BM25Index()
    merger = EngramMerger(store, vector, bm25)

    print("=== Engram Deduplication ===\n")
    result = merger.dedup_index()
    print(result["message"])


def cmd_decay(args: argparse.Namespace) -> None:
    """Apply priority decay to all engrams."""
    from src.storage.decay import PriorityDecay

    store = EngramStore()
    decay = PriorityDecay(store)

    print("=== Priority Decay ===\n")
    result = decay.apply_decay()
    print(result["message"])


def cmd_forget(args: argparse.Namespace) -> None:
    """Forget (delete) an engram."""
    from src.storage.forgetting import ForgettingManager

    store = EngramStore()
    fm = ForgettingManager(store)

    print(f"=== Forgetting Engram: {args.id} ===\n")
    if fm.forget(args.id, reason=getattr(args, 'reason', '')):
        print(f"Engram {args.id} forgotten.")
    else:
        print(f"Engram {args.id} not found.")


def cmd_forget_query(args: argparse.Namespace) -> None:
    """Forget engrams matching a query."""
    from src.storage.forgetting import ForgettingManager

    store = EngramStore()
    fm = ForgettingManager(store)

    print(f"=== Forgetting by Query: '{args.query}' ===\n")
    category = getattr(args, 'category', None)
    result = fm.forget_by_query(args.query, category=category)
    print(f"Matched: {result['matched']}")
    print(f"Forgetted: {result['forgotten']}")


def cmd_tiers(args: argparse.Namespace) -> None:
    """Show tier statistics."""
    from src.storage.decay import PriorityDecay

    store = EngramStore()
    decay = PriorityDecay(store)

    print("=== Memory Tiers ===\n")
    stats = decay.get_tier_stats()
    for tier_name, tier_data in stats.items():
        print(f"  {tier_name}:")
        print(f"    Count: {tier_data['count']}")
        print(f"    Avg Confidence: {tier_data['avg_confidence']:.3f}")
        print(f"    Categories: {', '.join(tier_data['categories'])}")
        print()


# ── CLI entry point ────────────────────────────────────────────────────────

def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="NeuralMemory — PLUR + Auto-Capture Fusion",
        prog="neural-memory",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # capture
    cap = subparsers.add_parser("capture", help="Capture an event as engram")
    cap.add_argument("event", help="JSON event string")

    # search (BM25)
    search = subparsers.add_parser("search", help="Search memories (BM25)")
    search.add_argument("query", help="Search query")
    search.add_argument("--top-k", type=int, default=10)

    # search-hybrid
    hybrid = subparsers.add_parser("search-hybrid", help="Hybrid BM25+vector search")
    hybrid.add_argument("query", help="Search query")
    hybrid.add_argument("--top-k", type=int, default=10)

    # similar
    similar = subparsers.add_parser("similar", help="Find similar engrams")
    similar.add_argument("statement", help="Statement to find similar engrams for")
    similar.add_argument("--top-k", type=int, default=10)

    # context
    context = subparsers.add_parser("context", help="Build context summary")
    context.add_argument("hours", nargs="?", type=int, default=24, help="Lookback hours")

    # recall
    recall = subparsers.add_parser("recall", help="Recall by category/type/domain")
    recall.add_argument("category", nargs="?", help="Category filter")
    recall.add_argument("--type", help="Type filter")
    recall.add_argument("--domain", help="Domain filter")
    recall.add_argument("--limit", type=int, default=50)

    # stats
    subparsers.add_parser("stats", help="Show memory stats")

    # list
    lst = subparsers.add_parser("list", help="List engrams")
    lst.add_argument("--limit", type=int, default=50)
    lst.add_argument("--offset", type=int, default=0)

    # delete
    delete = subparsers.add_parser("delete", help="Delete engram")
    delete.add_argument("id", help="Engram ID")

    # mcp
    subparsers.add_parser("mcp", help="Start MCP server")

    # demo
    subparsers.add_parser("demo", help="Run demo with sample data")

    # plur-sync
    plur_sync = subparsers.add_parser("plur-sync", help="Sync with PLUR: load engrams + show status")
    plur_sync.add_argument("--direction", choices=["both", "capture_only", "recall_only"],
                           help="Sync direction override")

    # plur-status
    subparsers.add_parser("plur-status", help="Show PLUR sync status")

    # plur-push
    plur_push = subparsers.add_parser("plur-push", help="Push pending engrams to PLUR")
    plur_push.add_argument("--dry-run", action="store_true", help="Show what would be pushed")

    # plur-clear
    subparsers.add_parser("plur-clear", help="Clear pending PLUR sync markers")

    # dedup
    subparsers.add_parser("dedup", help="Find and merge duplicate engrams")

    # decay
    subparsers.add_parser("decay", help="Apply priority decay to all engrams")

    # forget
    forget_cmd = subparsers.add_parser("forget", help="Forget (delete) an engram")
    forget_cmd.add_argument("id", help="Engram ID to forget")
    forget_cmd.add_argument("--reason", help="Reason for forgetting")

    # forget-query
    forget_query = subparsers.add_parser("forget-query", help="Forget engrams matching a query")
    forget_query.add_argument("query", help="Search query")
    forget_query.add_argument("--category", help="Optional category filter")

    # tiers
    subparsers.add_parser("tiers", help="Show tier statistics")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "capture": cmd_capture,
        "search": cmd_search,
        "search-hybrid": cmd_search_hybrid,
        "similar": cmd_similar,
        "context": cmd_context,
        "recall": cmd_recall,
        "stats": cmd_stats,
        "list": cmd_list,
        "delete": cmd_delete,
        "mcp": cmd_mcp,
        "demo": cmd_demo,
        "plur-sync": cmd_plur_sync,
        "plur-status": cmd_plur_status,
        "plur-push": cmd_plur_push,
        "plur-clear": cmd_plur_clear,
        "dedup": cmd_dedup,
        "decay": cmd_decay,
        "forget": cmd_forget,
        "forget-query": cmd_forget_query,
        "tiers": cmd_tiers,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
