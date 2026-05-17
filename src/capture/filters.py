"""Auto-capture filter rules.

Decides whether a tool-use event should be saved as an engram or ignored.
"""

import re
from dataclasses import dataclass
from enum import Enum

from src.config import config


class EventCategory(Enum):
    """Categories for auto-capture classification."""
    USER_CORRECTION = "user_correction"
    DEBUG_BREAKTHROUGH = "debug_breakthrough"
    NEW_WORKFLOW = "new_workflow"
    ARCHITECTURE_DECISION = "architecture_decision"
    API_QUIRK = "api_quirk"
    USER_PREFERENCE = "user_preference"
    BUDGET_CONSTRAINT = "budget_constraint"
    PROJECT_CONVENTION = "project_convention"
    ERROR_PATTERN = "error_pattern"
    TOOL_DISCOVERY = "tool_discovery"
    ROUTINE_FILE_READ = "routine_file_read"
    STANDARD_TERMINAL = "standard_terminal"
    GIT_OPERATION = "git_operations"
    CRON_LISTING = "cron_listings"
    SIMPLE_LOOKUP = "simple_lookups"
    UNKNOWN = "unknown"


@dataclass
class CaptureDecision:
    """Result of filter evaluation."""
    should_save: bool
    category: EventCategory
    confidence: float
    reason: str


# Patterns for classification: (compiled_regex, category, default_confidence)
_CLASSIFY_PATTERNS = [
    # High-confidence save patterns
    (re.compile(r'(?i)no, use \w+'), EventCategory.USER_CORRECTION, 0.95),
    (re.compile(r'(?i)(?:wrong|incorrect|that.s wrong|incorrectly)'), EventCategory.USER_CORRECTION, 0.9),
    (re.compile(r'(?i)(?:fixed|fix|resolved|solved).*(?:bug|error|issue)'), EventCategory.DEBUG_BREAKTHROUGH, 0.85),
    (re.compile(r'(?i)(?:root cause|root-cause|diagnos|traced).*(?:to|was|is)'), EventCategory.DEBUG_BREAKTHROUGH, 0.8),
    (re.compile(r'(?i)(?:new workflow|new approach|new pattern|discovered)'), EventCategory.NEW_WORKFLOW, 0.85),
    (re.compile(r'(?i)(?:decided|chose|going with).*(?:to use|to build|to implement)'), EventCategory.ARCHITECTURE_DECISION, 0.8),
    (re.compile(r'(?i)(?:gotcha|quirk|caveat|warning|note:).*(?:about|regarding|when)'), EventCategory.API_QUIRK, 0.85),
    (re.compile(r'(?i)(?:user prefers|user wants|user likes|user dislikes)'), EventCategory.USER_PREFERENCE, 0.9),
    (re.compile(r'(?i)(?:budget|cost|price|₹|rupee|expensive|cheap)'), EventCategory.BUDGET_CONSTRAINT, 0.8),
    (re.compile(r'(?i)(?:always use|never use|convention|standard).*(?:in this|for this|here)'), EventCategory.PROJECT_CONVENTION, 0.85),
    (re.compile(r'(?i)(?:retry|timeout|rate limit|backoff|exponential)'), EventCategory.ERROR_PATTERN, 0.8),
    (re.compile(r'(?i)(?:found|discovered|learned).*(?:tool|library|package|api)'), EventCategory.TOOL_DISCOVERY, 0.75),
    # Low-confidence ignore patterns
    (re.compile(r'(?i)^(?:git (?:add|commit|push|pull|fetch|merge|log|status|branch))'), EventCategory.GIT_OPERATION, 0.9),
    (re.compile(r'(?i)^(?:ls|cat |echo |pwd|whoami|uname|date|uptime)'), EventCategory.STANDARD_TERMINAL, 0.9),
    (re.compile(r'(?i)^(?:read_file|write_file|search_files|list_dir)'), EventCategory.ROUTINE_FILE_READ, 0.9),
    (re.compile(r'(?i)^(?:plur_list|cronjob.*list|skills_list)'), EventCategory.CRON_LISTING, 0.9),
    (re.compile(r'(?i)^(?:plur_status|plur_sync)'), EventCategory.SIMPLE_LOOKUP, 0.9),
]


class Filter:
    """Filter events to decide what to save."""

    def __init__(self) -> None:
        self._save_categories = set(config.get("filters.save", []))
        self._ignore_categories = set(config.get("filters.ignore", []))

    def evaluate(self, event: dict) -> CaptureDecision:
        """Evaluate whether to save an event.

        Args:
            event: Tool use event dict with keys like:
                - tool_name: str
                - input: dict
                - output: str
                - user_message: str (optional)

        Returns:
            CaptureDecision with save/ignore verdict
        """
        # Extract text from event for classification
        text_parts = []
        text_parts.append(event.get("tool_name", ""))
        text_parts.append(str(event.get("output", "")))
        text_parts.append(str(event.get("user_message", "")))
        text_parts.append(str(event.get("error", "")))
        text = " ".join(text_parts)
        matched_confidence = 0.0

        # Check save patterns first (higher priority)
        for pattern, category, confidence in _CLASSIFY_PATTERNS:
            cat_value = category.value if isinstance(category, EventCategory) else category
            if cat_value in self._save_categories:
                if pattern.search(text):
                    return CaptureDecision(
                        should_save=True,
                        category=category if isinstance(category, EventCategory) else EventCategory(cat_value),
                        confidence=confidence,
                        reason=f"Matched: {cat_value} (confidence={confidence:.2f})"
                    )
                matched_confidence = max(matched_confidence, confidence)

        # Then check ignore patterns
        for pattern, category, confidence in _CLASSIFY_PATTERNS:
            cat_value = category.value if isinstance(category, EventCategory) else category
            if cat_value in self._ignore_categories:
                if pattern.search(text):
                    return CaptureDecision(
                        should_save=False,
                        category=category if isinstance(category, EventCategory) else EventCategory(cat_value),
                        confidence=confidence,
                        reason=f"Ignored: {cat_value}"
                    )
                matched_confidence = max(matched_confidence, confidence)

        # No pattern matched - use confidence threshold
        min_confidence = config.get("capture.min_confidence", 0.6)
        if matched_confidence >= min_confidence:
            return CaptureDecision(
                should_save=True,
                category=EventCategory.UNKNOWN,
                confidence=matched_confidence,
                reason=f"Passed confidence threshold ({matched_confidence:.2f} >= {min_confidence})"
            )

        return CaptureDecision(
            should_save=False,
            category=EventCategory.UNKNOWN,
            confidence=matched_confidence,
            reason=f"Below confidence threshold ({matched_confidence:.2f} < {min_confidence})"
        )

    def classify(self, event: dict) -> EventCategory:
        """Just classify without save/ignore logic."""
        text_parts = [
            event.get("tool_name", ""),
            str(event.get("output", "")),
            str(event.get("user_message", "")),
        ]
        text = " ".join(text_parts)

        for pattern, category, _ in _CLASSIFY_PATTERNS:
            cat_value = category.value if isinstance(category, EventCategory) else category
            if cat_value in self._save_categories or cat_value in self._ignore_categories:
                if pattern.search(text):
                    return category if isinstance(category, EventCategory) else EventCategory(cat_value)
        return EventCategory.UNKNOWN
