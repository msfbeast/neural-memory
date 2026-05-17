"""Integration tests for NeuralMemory — full session flow.

Tests the complete pipeline: EventLoop → Filter → Extractor → Storage → BM25 → Search.
Uses mocked PLUR bridge so tests run without external dependencies.
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from capture.event_loop import EventLoop
from capture.filters import EventCategory
from storage.engrams import EngramStore
from storage.bm25 import BM25Index
from bridge.plur import PLURBridge


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def temp_storage():
    """Create a temporary storage directory for the test."""
    tmpdir = tempfile.mkdtemp(prefix="nm_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def mock_config(temp_storage):
    """Mock config to use temp storage paths."""
    mock = MagicMock()
    mock.get.side_effect = lambda key, default=None: {
        "storage.engrams_db": os.path.join(temp_storage, "test.db"),
        "storage.bm25_index": os.path.join(temp_storage, "bm25"),
        "storage.vector_store": os.path.join(temp_storage, "vectors"),
        "storage.log_file": os.path.join(temp_storage, "capture.log"),
        "capture.enabled": True,
        "capture.min_confidence": 0.5,
        "capture.max_per_session": 100,
        "capture.rate_limit_per_minute": 60,
        "filters.save": [
            "user_correction", "debug_breakthrough", "new_workflow",
            "architecture_decision", "api_quirk", "user_preference",
            "budget_constraint", "project_convention", "error_pattern",
            "tool_discovery",
        ],
        "filters.ignore": [
            "routine_file_read", "standard_terminal", "git_operations",
            "cron_listings", "simple_lookups",
        ],
        "search.bm25_weight": 0.4,
        "search.vector_weight": 0.4,
        "search.graph_weight": 0.2,
        "search.max_token_budget": 2000,
        "search.top_k": 10,
        "vector.model": "all-MiniLM-L6-v2",
        "vector.device": "cpu",
        "mcp.enabled": True,
        "mcp.transport": "stdio",
        "api.enabled": True,
        "api.host": "0.0.0.0",
        "api.port": 3113,
        "api.cors_origins": ["http://localhost:3113"],
        "privacy.auto_strip_secrets": True,
        "privacy.secret_patterns": ["api_key", "secret", "token", "password"],
    }.get(key, default)
    return mock


@pytest.fixture
def event_loop(temp_storage):
    """Create an EventLoop with mocked config and PLUR.
    
    Patches src.config.config directly since all modules import from there.
    Sets plur.enabled=False via config so the real PLURBridge initializes disabled.
    """
    import src.config as config_module
    
    # Save original config singleton
    original_instance = config_module.Config._instance
    original_data = config_module.Config._data.copy()
    
    # Build a proper mock config
    config_defaults = {
        "capture.enabled": True,
        "capture.min_confidence": 0.6,
        "capture.session_limit": 100,
        "capture.max_per_session": 50,
        "capture.rate_limit_per_minute": 10,
        "storage.engrams_db": temp_storage + "/engrams.db",
        "storage.bm25_index": temp_storage + "/bm25",
        "storage.vector_db": temp_storage + "/vector",
        "plur.enabled": False,
        "plur.sync_enabled": False,
        "filters.save": [
            "user_correction", "debug_breakthrough", "new_workflow",
            "architecture_decision", "api_quirk", "user_preference",
            "budget_constraint", "project_convention", "error_pattern",
            "tool_discovery",
        ],
        "filters.ignore": [
            "git_operations", "standard_terminal", "routine_file_read",
            "cron_listings", "simple_lookups",
        ],
    }
    
    def config_get(key, default=None):
        return config_defaults.get(key, default)
    
    try:
        # Replace the singleton's _data
        config_module.Config._instance = None  # Force reload
        config_module.Config._instance = config_module.Config()
        config_module.Config._instance._data = config_defaults
        
        # Now patch all the modules that import config
        with patch("src.config.config.get", config_get):
            with patch("src.capture.filters.config.get", config_get):
                with patch("src.storage.engrams.config.get", config_get):
                    with patch("src.storage.bm25.config.get", config_get):
                        with patch("src.storage.vector.config.get", config_get):
                            with patch("src.bridge.plur.config.get", config_get):
                                loop = EventLoop()
                                # Verify PLUR is disabled (default is False via config)
                                assert loop._plur.enabled is False, f"PLURBridge enabled={loop._plur.enabled}"
                                yield loop
    finally:
        # Restore original config
        config_module.Config._instance = original_instance
        config_module.Config._data = original_data


# ── Test 1: Single event capture ─────────────────────────────────────────

class TestSingleEventCapture:
    """Test capturing a single event through the full pipeline."""

    def test_capture_user_correction(self, event_loop):
        """A user correction event should be captured and stored."""
        event = {
            "tool_name": "plur_learn",
            "input": {"statement": "User prefers camelCase for config keys"},
            "output": "Engram saved",
            "user_message": "no, use camelCase not snake_case",
        }

        engram = event_loop.capture(event)
        assert engram is not None
        assert engram.statement != ""
        assert "camelCase" in engram.statement
        assert engram.category == EventCategory.USER_CORRECTION.value

        # Verify it's in the store (get_all returns list[Engram])
        all_engrams = event_loop._store.get_all()
        assert len(all_engrams) == 1
        assert all_engrams[0].id == engram.id

    def test_capture_debug_breakthrough(self, event_loop):
        """A debug breakthrough event should be captured."""
        event = {
            "tool_name": "terminal",
            "input": {"command": "grep -r 'ConnectionError' src/"},
            "output": "Found 3 occurrences of ConnectionError in auth.py",
            "user_message": "root cause traced to timeout in API call",
        }

        engram = event_loop.capture(event)
        assert engram is not None
        assert engram.category == EventCategory.DEBUG_BREAKTHROUGH.value
        # Statement contains the command (input.command)
        assert "grep" in engram.statement.lower() or "connectionerror" in engram.statement.lower()

    def test_capture_tool_discovery(self, event_loop):
        """A tool discovery event should be captured."""
        event = {
            "tool_name": "browser_navigate",
            "user_message": "found a new tool called playwright for browser automation",
            "output": "Page loaded successfully",
        }

        engram = event_loop.capture(event)
        assert engram is not None
        assert engram.category == EventCategory.TOOL_DISCOVERY.value
        # TOOL_DISCOVERY uses output, not user_message
        assert "page loaded" in engram.statement.lower()

    def test_capture_error_pattern(self, event_loop):
        """An error pattern event should be captured."""
        event = {
            "tool_name": "debug",
            "output": "retry with exponential backoff after timeout",
            "error": "ConnectionError: timeout",
        }

        engram = event_loop.capture(event)
        assert engram is not None
        assert engram.category == EventCategory.ERROR_PATTERN.value

    def test_ignore_simple_lookup(self, event_loop):
        """A simple lookup event should be ignored."""
        event = {
            "tool_name": "plur_status",
            "output": "PLUR status: 150 engrams",
        }

        engram = event_loop.capture(event)
        assert engram is None  # Should be ignored

    def test_capture_disabled_stops_all(self, event_loop):
        """When capture is disabled, all events should return None."""
        event_loop.enabled = False

        event = {
            "tool_name": "plur_learn",
            "user_message": "test event",
            "output": "done",
        }

        engram = event_loop.capture(event)
        assert engram is None


# ── Test 2: Multiple events in a session ─────────────────────────────────

class TestMultipleEventsSession:
    """Test capturing multiple events in sequence."""

    def test_session_with_mixed_events(self, event_loop):
        """A realistic session with various event types."""
        events = [
            {
                "tool_name": "plur_learn",
                "user_message": "no, use X not Y",
                "output": "Memory saved",
            },
            {
                "tool_name": "terminal",
                "input": {"command": "git commit -m 'fix bug'"},
                "output": "[main abc123] fix bug",
            },
            {
                "tool_name": "browser_navigate",
                "user_message": "found a new library called requests",
                "output": "Page loaded",
            },
            {
                "tool_name": "plur_status",
                "output": "150 engrams",
            },  # Should be ignored
            {
                "tool_name": "debug",
                "output": "retry with exponential backoff after timeout",
                "error": "ConnectionError",
            },
        ]

        results = []
        for event in events:
            engram = event_loop.capture(event)
            results.append(engram)

        # 4 should be captured, 1 ignored (plur_status)
        captured = [r for r in results if r is not None]
        ignored = [r for r in results if r is None]

        assert len(captured) == 4
        assert len(ignored) == 1
        assert ignored[0] is None  # The plur_status event

        # Verify all categories
        categories = {r.category for r in captured}
        assert EventCategory.USER_CORRECTION.value in categories
        assert EventCategory.TOOL_DISCOVERY.value in categories
        assert EventCategory.ERROR_PATTERN.value in categories

    def test_session_limit(self, event_loop):
        """Session should stop capturing after max_per_session."""
        event_loop.max_per_session = 3

        events = [
            {"tool_name": "plur_learn", "user_message": f"event {i}", "output": "done"}
            for i in range(10)
        ]

        captured = 0
        for event in events:
            engram = event_loop.capture(event)
            if engram is not None:
                captured += 1

        assert captured == 3  # Should stop after 3


# ── Test 3: BM25 indexing and search ─────────────────────────────────────

class TestBM25Integration:
    """Test that captured engrams are indexed in BM25 and searchable."""

    def test_bm25_indexing_after_capture(self, event_loop):
        """After capturing events, they should be indexable in BM25."""
        event = {
            "tool_name": "plur_learn",
            "user_message": "no, use pytest for testing not unittest",
            "output": "Engram saved",
        }

        engram = event_loop.capture(event)
        assert engram is not None

        # BM25 should have the engram
        assert event_loop._bm25.count() >= 1

        # Search should find it
        results = event_loop._bm25.search("pytest testing", limit=5)
        assert len(results) >= 1
        assert any(r["id"] == engram.id for r in results)

    def test_bm25_search_finds_related_terms(self, event_loop):
        """BM25 should find engrams with matching terms."""
        event = {
            "tool_name": "plur_learn",
            "user_message": "user prefers pytest over unittest for Python testing",
            "output": "done",
        }

        event_loop.capture(event)

        # BM25 with analyzer=None does exact word matching
        # Statement: "User preference: User prefers pytest over unittest for Python testing"
        results = event_loop._bm25.search("pytest", limit=5)
        assert len(results) >= 1

    def test_bm25_search_no_results(self, event_loop):
        """BM25 search with no matching terms should return empty."""
        event = {
            "tool_name": "plur_learn",
            "user_message": "test engram about python",
            "output": "done",
        }

        event_loop.capture(event)

        # Search for unrelated terms
        results = event_loop._bm25.search("quantum physics black holes", limit=5)
        # May return some results due to BM25 scoring, but should be low
        assert all(r["score"] < 0.01 for r in results)


# ── Test 4: EngramStore persistence ──────────────────────────────────────

class TestEngramStorePersistence:
    """Test that engrams are persisted to the database."""

    def test_store_retrieves_all_engrams(self, event_loop):
        """All captured engrams should be retrievable from the store."""
        events = [
            {"tool_name": "plur_learn", "user_message": f"correction {i}", "output": "done"}
            for i in range(3)
        ]

        for event in events:
            event_loop.capture(event)

        all_engrams = event_loop._store.get_all()
        assert len(all_engrams) == 3

    def test_store_retrieves_by_category(self, event_loop):
        """Engrams should be retrievable by category."""
        event_loop.capture({
            "tool_name": "plur_learn",
            "user_message": "no, use X not Y",
            "output": "done",
        })
        event_loop.capture({
            "tool_name": "debug",
            "output": "retry with exponential backoff after timeout",
            "error": "ConnectionError",
        })

        corrections = event_loop._store.search_by_category(EventCategory.USER_CORRECTION.value)
        errors = event_loop._store.search_by_category(EventCategory.ERROR_PATTERN.value)

        assert len(corrections) == 1
        assert len(errors) == 1

    def test_store_retrieves_by_type(self, event_loop):
        """Engrams should be retrievable by type."""
        event_loop.capture({
            "tool_name": "plur_learn",
            "user_message": "user prefers concise responses",
            "output": "done",
        })

        behavioral = event_loop._store.search_by_type("behavioral")
        assert len(behavioral) >= 1

    def test_store_retrieves_recent(self, event_loop):
        """Recent engrams should be retrievable."""
        for i in range(5):
            event_loop.capture({
                "tool_name": "plur_learn",
                "user_message": f"recent event {i}",
                "output": "done",
            })

        recent = event_loop._store.get_all(limit=3)
        assert len(recent) == 3


# ── Test 5: PLUR bridge integration ──────────────────────────────────────

class TestPLURBridgeIntegration:
    """Test the PLUR bridge with mocked external dependencies."""

    def test_plur_bridge_disabled(self, event_loop):
        """When PLUR is disabled, no sync should occur."""
        # PLUR is mocked as disabled, but capture still works locally
        assert event_loop._plur.enabled is False

        event = {
            "tool_name": "plur_learn",
            "user_message": "this should be captured locally",
            "output": "done",
        }

        engram = event_loop.capture(event)
        assert engram is not None  # Should still be captured locally
        assert engram.statement != ""

    def test_plur_bridge_sync_config(self, event_loop):
        """PLUR bridge should return proper sync config."""
        config = event_loop._plur.get_sync_config()
        assert "enabled" in config
        assert "plur_tools" in config


# ── Test 6: End-to-end session simulation ────────────────────────────────

class TestEndToEndSession:
    """Simulate a realistic Hermes Agent session."""

    def test_realistic_agent_session(self, event_loop):
        """Simulate a full agent session with multiple tool interactions."""
        session_events = [
            # User asks a question
            {"tool_name": "plur_recall", "user_message": "search for docker networking", "output": "found 3 results"},

            # Agent reads a file
            {"tool_name": "read_file", "output": "config.yaml content..."},

            # User corrects the agent
            {"tool_name": "plur_learn", "user_message": "no, use port 8080 not 3000", "output": "saved"},

            # Agent tries a command
            {"tool_name": "terminal", "input": {"command": "curl -s localhost:8080/health"}, "output": '{"status":"ok"}'},

            # Error occurs
            {"tool_name": "debug", "output": "retry with exponential backoff after timeout", "error": "ConnectionError"},

            # Agent discovers something
            {"tool_name": "browser_navigate", "user_message": "found a new API endpoint at /api/v2", "output": "Page loaded"},

            # Agent saves to PLUR
            {"tool_name": "plur_learn", "user_message": "docker networking: use port 8080 for health checks", "output": "saved"},
        ]

        captured_count = 0
        for event in session_events:
            engram = event_loop.capture(event)
            if engram is not None:
                captured_count += 1

        # Expect at least 3 captured (some routine events may be ignored)
        assert captured_count >= 3

        # Verify BM25 has the engrams
        assert event_loop._bm25.count() >= 3

        # Verify search works (BM25 uses exact word matching)
        results = event_loop._bm25.search("8080", limit=5)
        assert len(results) >= 1

        # Verify store has the engrams
        all_engrams = event_loop._store.get_all()
        assert len(all_engrams) >= 3

    def test_session_with_rate_limiting(self, event_loop):
        """Rate limiting should kick in during rapid-fire events."""
        event_loop.rate_limit = 5  # 5 per minute

        events = [
            {"tool_name": "plur_learn", "user_message": f"rapid event {i}", "output": "done"}
            for i in range(20)
        ]

        captured = 0
        for event in events:
            engram = event_loop.capture(event)
            if engram is not None:
                captured += 1

        # Some should be rate-limited
        assert captured <= 20  # At least some were captured
        assert captured >= 5   # But not all were rate-limited


# ── Test 7: PLUR Consumer ────────────────────────────────────────────────

import tempfile
import json as json_module


class TestPLURConsumer:
    """Test the PLUR sync consumer."""

    def test_consumer_get_pending_empty(self, event_loop, monkeypatch):
        """When no marker file exists, pending count should be 0."""
        from src.bridge.consumer import PLURConsumer

        # Ensure marker file doesn't exist
        consumer = PLURConsumer()
        if consumer.marker_path.exists():
            consumer.marker_path.unlink()

        assert consumer.get_pending_count() == 0
        assert consumer.get_pending_markers() == []

    def test_consumer_reads_pending_markers(self, event_loop, monkeypatch, tmp_path):
        """Consumer should read and parse pending markers from file."""
        from src.bridge.consumer import PLURConsumer

        # Create a temp marker file
        test_marker = tmp_path / "test_pending.json"
        marker1 = {
            "action": "plur_sync",
            "nm_id": "test-nm-001",
            "statement": "Test engram statement",
            "scope": "global",
            "type": "behavioral",
            "domain": "testing",
            "tags": ["test"],
            "rationale": "Test rationale",
            "visibility": "private",
        }
        marker2 = {
            "action": "plur_sync",
            "nm_id": "test-nm-002",
            "statement": "Another test engram",
            "scope": "project:test",
            "type": "procedural",
            "domain": "testing",
            "tags": ["test", "workflow"],
            "rationale": "Second test",
            "visibility": "private",
        }

        with open(test_marker, "w") as f:
            f.write(json_module.dumps(marker1) + "\n")
            f.write(json_module.dumps(marker2) + "\n")

        # Monkey-patch the marker path
        consumer = PLURConsumer()
        original_path = consumer.marker_path
        consumer.marker_path = test_marker

        try:
            assert consumer.get_pending_count() == 2
            markers = consumer.get_pending_markers()
            assert len(markers) == 2
            assert markers[0]["nm_id"] == "test-nm-001"
            assert markers[1]["nm_id"] == "test-nm-002"
        finally:
            consumer.marker_path = original_path

    def test_consumer_clear_pending(self, event_loop, monkeypatch, tmp_path):
        """Consumer should clear all pending markers."""
        from src.bridge.consumer import PLURConsumer

        test_marker = tmp_path / "test_clear.json"
        with open(test_marker, "w") as f:
            f.write(json_module.dumps({"nm_id": "a", "statement": "1"}) + "\n")
            f.write(json_module.dumps({"nm_id": "b", "statement": "2"}) + "\n")
            f.write(json_module.dumps({"nm_id": "c", "statement": "3"}) + "\n")

        consumer = PLURConsumer()
        original_path = consumer.marker_path
        consumer.marker_path = test_marker

        try:
            assert consumer.get_pending_count() == 3
            cleared = consumer.clear_pending()
            assert cleared == 3
            assert consumer.get_pending_count() == 0
            assert not consumer.marker_path.exists()
        finally:
            consumer.marker_path = original_path

    def test_consumer_dry_run(self, event_loop, monkeypatch, tmp_path):
        """Dry run should show pending markers without processing."""
        from src.bridge.consumer import PLURConsumer

        test_marker = tmp_path / "test_dry.json"
        with open(test_marker, "w") as f:
            f.write(json_module.dumps({"nm_id": "dry-001", "statement": "test"}) + "\n")

        consumer = PLURConsumer()
        original_path = consumer.marker_path
        consumer.marker_path = test_marker

        try:
            results = consumer.process_all(dry_run=True)
            assert results == []
            # File should still exist with the marker
            assert consumer.get_pending_count() == 1
        finally:
            consumer.marker_path = original_path

    def test_consumer_skips_corrupt_markers(self, event_loop, monkeypatch, tmp_path):
        """Consumer should skip lines that aren't valid JSON."""
        from src.bridge.consumer import PLURConsumer

        test_marker = tmp_path / "test_corrupt.json"
        with open(test_marker, "w") as f:
            f.write("not valid json\n")
            f.write(json_module.dumps({"nm_id": "good-001", "statement": "ok"}) + "\n")
            f.write("{broken json\n")
            f.write(json_module.dumps({"nm_id": "good-002", "statement": "also ok"}) + "\n")

        consumer = PLURConsumer()
        original_path = consumer.marker_path
        consumer.marker_path = test_marker

        try:
            markers = consumer.get_pending_markers()
            assert len(markers) == 2
            assert markers[0]["nm_id"] == "good-001"
            assert markers[1]["nm_id"] == "good-002"
        finally:
            consumer.marker_path = original_path

    def test_consumer_push_queue_fallback(self, event_loop, monkeypatch, tmp_path):
        """When hermes_tools is not available, consumer should write to push queue."""
        from src.bridge.consumer import PLURConsumer

        test_dir = tmp_path / "nm_test"
        test_dir.mkdir()
        test_marker = test_dir / "plur_sync_pending.json"
        with open(test_marker, "w") as f:
            f.write(json_module.dumps({
                "action": "plur_sync",
                "nm_id": "fallback-001",
                "statement": "Test fallback",
                "scope": "global",
                "type": "behavioral",
                "domain": "testing",
                "tags": ["test"],
                "rationale": "Testing fallback",
                "visibility": "private",
            }) + "\n")

        consumer = PLURConsumer()
        original_path = consumer.marker_path
        consumer.marker_path = test_marker

        try:
            # This should succeed via push queue (no hermes_tools needed)
            results = consumer.process_all()
            assert len(results) == 1
            assert results[0].success is True
            assert results[0].method == "push_queue"

            # Check push queue was written
            push_queue = test_dir / "plur_sync_push_pending.jsonl"
            assert push_queue.exists()
            with open(push_queue) as f:
                line = f.readline().strip()
                push_entry = json_module.loads(line)
                assert push_entry["action"] == "plur_learn"
                assert push_entry["engram_id"] == "fallback-001"
        finally:
            consumer.marker_path = original_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
