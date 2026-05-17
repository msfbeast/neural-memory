"""Tests for the PLUR push queue PostToolUse hook."""

import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import plur_push


class TestReadPushQueue:
    def test_empty_queue(self, monkeypatch, tmp_path):
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", tmp_path / "nonexistent.jsonl")
        assert plur_push.read_push_queue() == []

    def test_single_entry(self, monkeypatch, tmp_path):
        queue_path = tmp_path / "plur_sync_push_pending.jsonl"
        entry = {"action": "plur_learn", "statement": "test engram", "engram_id": "test-1"}
        queue_path.write_text(json.dumps(entry) + "\n")
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", queue_path)
        result = plur_push.read_push_queue()
        assert len(result) == 1
        assert result[0]["statement"] == "test engram"

    def test_multiple_entries(self, monkeypatch, tmp_path):
        queue_path = tmp_path / "plur_sync_push_pending.jsonl"
        entries = [
            {"statement": "first", "engram_id": "1"},
            {"statement": "second", "engram_id": "2"},
            {"statement": "third", "engram_id": "3"},
        ]
        queue_path.write_text("".join(json.dumps(e) + "\n" for e in entries))
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", queue_path)
        result = plur_push.read_push_queue()
        assert len(result) == 3

    def test_skips_corrupt_lines(self, monkeypatch, tmp_path):
        queue_path = tmp_path / "plur_sync_push_pending.jsonl"
        content = '{"statement": "valid"}\nnot json\n{"statement": "also valid"}\n'
        queue_path.write_text(content)
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", queue_path)
        result = plur_push.read_push_queue()
        assert len(result) == 2
        assert result[0]["statement"] == "valid"
        assert result[1]["statement"] == "also valid"


class TestWritePushQueue:
    def test_writes_entries(self, monkeypatch, tmp_path):
        queue_path = tmp_path / "plur_sync_push_pending.jsonl"
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", queue_path)
        entries = [
            {"statement": "test", "engram_id": "1"},
            {"statement": "test2", "engram_id": "2"},
        ]
        plur_push.write_push_queue(entries)
        lines = queue_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["statement"] == "test"
        assert json.loads(lines[1])["statement"] == "test2"

    def test_overwrites_existing(self, monkeypatch, tmp_path):
        queue_path = tmp_path / "plur_sync_push_pending.jsonl"
        queue_path.write_text('{"old": "data"}\n')
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", queue_path)
        plur_push.write_push_queue([{"new": "data"}])
        lines = queue_path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["new"] == "data"


class TestCallPlurLearn:
    def test_success(self, monkeypatch):
        mock_plur_learn = mock.MagicMock(return_value={"success": True})
        monkeypatch.setattr(plur_push, "plur_learn", mock_plur_learn)

        result = plur_push.call_plur_learn({
            "statement": "test", "scope": "global", "type": "behavioral",
            "domain": "neural_memory", "tags": [], "rationale": "", "visibility": "private",
        })
        assert result["success"] is True
        mock_plur_learn.assert_called_once()

    def test_missing_hermes_tools(self):
        # Ensure hermes_tools is not imported
        if "hermes_tools" in sys.modules:
            del sys.modules["hermes_tools"]
        result = plur_push.call_plur_learn({"statement": "test"})
        assert result["success"] is False
        assert "not available" in result["message"]

    def test_plur_learn_error(self, monkeypatch):
        mock_plur_learn = mock.MagicMock(side_effect=Exception("API error"))
        monkeypatch.setattr(plur_push, "plur_learn", mock_plur_learn)

        result = plur_push.call_plur_learn({"statement": "test"})
        assert result["success"] is False
        assert "API error" in result["message"]


class TestMain:
    def test_no_queue_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", tmp_path / "nonexistent.jsonl")
        mock_stdin = mock.MagicMock()
        mock_stdin.read.return_value = '{"tool_name": "terminal"}'
        monkeypatch.setattr(sys, "stdin", mock_stdin)
        # Should exit silently with no error
        try:
            plur_push.main()
        except SystemExit:
            pass  # Expected - exits with code 0 when queue is empty

    def test_empty_queue_exits_early(self, monkeypatch, tmp_path):
        queue_path = tmp_path / "plur_sync_push_pending.jsonl"
        queue_path.write_text("")
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", queue_path)
        mock_stdin = mock.MagicMock()
        mock_stdin.read.return_value = '{"tool_name": "terminal"}'
        monkeypatch.setattr(sys, "stdin", mock_stdin)

        # Should exit without processing
        with mock.patch.object(plur_push, "call_plur_learn") as mock_call:
            try:
                plur_push.main()
            except SystemExit:
                pass  # Expected - exits with code 0 when queue is empty
            mock_call.assert_not_called()

    def test_processes_entries(self, monkeypatch, tmp_path):
        queue_path = tmp_path / "plur_sync_push_pending.jsonl"
        entry = {"statement": "test engram", "engram_id": "1"}
        queue_path.write_text(json.dumps(entry) + "\n")
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", queue_path)
        mock_stdin = mock.MagicMock()
        mock_stdin.read.return_value = '{"tool_name": "terminal"}'
        monkeypatch.setattr(sys, "stdin", mock_stdin)

        mock_plur_learn = mock.MagicMock(return_value={"success": True})
        monkeypatch.setattr(plur_push, "plur_learn", mock_plur_learn)

        try:
            plur_push.main()
        except SystemExit:
            pass
        mock_plur_learn.assert_called_once()
        # Queue file should be removed after processing
        assert not queue_path.exists()

    def test_fails_remain_in_queue(self, monkeypatch, tmp_path):
        queue_path = tmp_path / "plur_sync_push_pending.jsonl"
        entry = {"statement": "test engram", "engram_id": "1"}
        queue_path.write_text(json.dumps(entry) + "\n")
        monkeypatch.setattr(plur_push, "PUSH_QUEUE_PATH", queue_path)
        mock_stdin = mock.MagicMock()
        mock_stdin.read.return_value = '{"tool_name": "terminal"}'
        monkeypatch.setattr(sys, "stdin", mock_stdin)

        # hermes_tools not available -> fails
        if "hermes_tools" in sys.modules:
            del sys.modules["hermes_tools"]

        try:
            plur_push.main()
        except SystemExit:
            pass
        # Queue file should still exist with the failed entry
        assert queue_path.exists()
        lines = queue_path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["statement"] == "test engram"
