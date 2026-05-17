"""Config loader for NeuralMemory."""

import os
import yaml
from pathlib import Path
from typing import Any, Optional


class Config:
    """Load and manage NeuralMemory configuration."""

    _instance: Optional["Config"] = None
    _data: dict[str, Any] = {}

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """Load config from YAML file or defaults."""
        config_path = Path(os.environ.get(
            "NEURAL_MEMORY_CONFIG",
            os.path.expanduser("~/.plur/neural-memory/config.yaml")
        ))

        if config_path.exists():
            with open(config_path) as f:
                self._data = yaml.safe_load(f) or {}
        else:
            # Defaults
            self._data = self._defaults()

        # Override with env vars
        self._apply_env_overrides()

    def _defaults(self) -> dict[str, Any]:
        return {
            "storage": {
                "engrams_db": os.path.expanduser("~/.plur/neural_memory/engrams.db"),
                "bm25_index": os.path.expanduser("~/.plur/neural_memory/bm25_index"),
                "vector_store": os.path.expanduser("~/.plur/neural_memory/vector_store"),
                "log_file": os.path.expanduser("~/.plur/neural_memory/capture.log"),
            },
            "capture": {
                "enabled": True,
                "min_confidence": 0.6,
                "max_per_session": 50,
                "rate_limit_per_minute": 10,
            },
            "filters": {
                "save": [
                    "user_correction", "debug_breakthrough", "new_workflow",
                    "architecture_decision", "api_quirk", "user_preference",
                    "budget_constraint", "project_convention", "error_pattern",
                    "tool_discovery",
                ],
                "ignore": [
                    "routine_file_read", "standard_terminal", "git_operations",
                    "cron_listings", "simple_lookups",
                ],
            },
            "search": {
                "bm25_weight": 0.4,
                "vector_weight": 0.4,
                "graph_weight": 0.2,
                "max_token_budget": 2000,
                "top_k": 10,
            },
            "tiers": {
                "working": {"decay_hours": 1, "plurs_type": None},
                "episodic": {"decay_days": 7, "plurs_type": "behavioral"},
                "semantic": {"decay_days": 30, "plurs_type": "terminological,behavioral"},
                "procedural": {"decay_days": 90, "plurs_type": "procedural,architectural"},
            },
            "vector": {
                "model": "all-MiniLM-L6-v2",
                "device": "mps",
            },
            "mcp": {
                "enabled": True,
                "transport": "stdio",
            },
            "api": {
                "enabled": True,
                "host": "0.0.0.0",
                "port": 3113,
                "cors_origins": ["http://localhost:3113"],
            },
            "privacy": {
                "auto_strip_secrets": True,
                "secret_patterns": [
                    "api[_-]?key", "secret", "token", "password",
                    "credential", "private[_-]?key",
                ],
            },
        }

    def _apply_env_overrides(self) -> None:
        """Allow env vars to override config values."""
        if db := os.environ.get("NM_ENGRAMS_DB"):
            self._data["storage"]["engrams_db"] = db
        if port := os.environ.get("NM_API_PORT"):
            self._data["api"]["port"] = int(port)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot notation. e.g. 'storage.engrams_db'."""
        keys = key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
            if val is None:
                return default
        return val

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __repr__(self) -> str:
        return f"Config(storage={self['storage']['engrams_db']})"


# Global config singleton
config = Config()
