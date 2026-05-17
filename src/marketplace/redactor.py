"""Privacy-first redaction engine.

Strips sensitive data from engrams before sharing to the marketplace.
All memories are private by default — only explicitly shared memories
go through redaction and publication.
"""

import re
from typing import Optional
from dataclasses import dataclass, field

from src.capture.extractor import Engram


# Patterns that indicate sensitive data
SENSITIVE_PATTERNS = [
    # API keys and tokens
    (r'(?:api[_-]?key|secret|token|password|credential|private[_-]?key)\s*[:=]\s*["\']?([A-Za-z0-9_\-./+=]{16,})["\']?', '[REDACTED_API_KEY]'),
    # GitHub tokens
    (r'ghp_[A-Za-z0-9]{36}', '[REDACTED_GITHUB_TOKEN]'),
    (r'gho_[A-Za-z0-9]{36}', '[REDACTED_GITHUB_TOKEN]'),
    # Generic base64-ish tokens
    (r'(?:eyJ|eyJh|eyJp)[A-Za-z0-9+/=_-]{20,}', '[REDACTED_JWT]'),
    # File paths (absolute) — keep relative paths
    (r'/(?:Users|home|root)/[A-Za-z0-9_.-]+/[^"\'\s,]+', '[REDACTED_PATH]'),
    # Email addresses
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[REDACTED_EMAIL]'),
    # Phone numbers
    (r'\+?[\d\s\-()]{10,}', '[REDACTED_PHONE]'),
    # IP addresses
    (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[REDACTED_IP]'),
    # Credit card patterns
    (r'\b(?:\d{4}[-\s]?){3}\d{4}\b', '[REDACTED_CC]'),
    # AWS keys
    (r'(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}', '[REDACTED_AWS_KEY]'),
]


@dataclass
class RedactionResult:
    """Result of redacting an engram."""
    redacted_statement: str
    redacted_rationale: Optional[str] = None
    redacted_extra: dict = field(default_factory=dict)
    redacted_count: int = 0
    redacted_fields: list[str] = field(default_factory=list)


class Redactor:
    """Redact sensitive data from engrams before sharing."""

    def __init__(self) -> None:
        self._compiled = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in SENSITIVE_PATTERNS
        ]

    def redact(self, engram: Engram) -> RedactionResult:
        """Redact sensitive data from an engram.

        Returns a RedactionResult with the redacted fields.
        The original engram is NOT modified — returns a new dict.
        """
        statement = engram.statement or ""
        rationale = engram.rationale or ""
        extra: dict = {}

        redacted_count = 0
        redacted_fields = []

        # Redact statement
        for pattern, replacement in self._compiled:
            matches = pattern.findall(statement)
            if matches:
                redacted_count += len(matches)
                statement = pattern.sub(replacement, statement)
                redacted_fields.append(f"statement:{len(matches)}")

        # Redact rationale
        for pattern, replacement in self._compiled:
            matches = pattern.findall(rationale)
            if matches:
                redacted_count += len(matches)
                rationale = pattern.sub(replacement, rationale)
                redacted_fields.append(f"rationale:{len(matches)}")

        # Redact tags (unlikely but safe)
        safe_tags = []
        for tag in engram.tags:
            redacted_tag = tag
            for pattern, replacement in self._compiled:
                redacted_tag = pattern.sub(replacement, redacted_tag)
            safe_tags.append(redacted_tag)

        return RedactionResult(
            redacted_statement=statement,
            redacted_rationale=rationale if rationale != engram.rationale else None,
            redacted_extra={"redacted_tags": safe_tags if safe_tags != engram.tags else None},
            redacted_count=redacted_count,
            redacted_fields=redacted_fields,
        )

    def is_safe(self, engram: Engram) -> bool:
        """Check if an engram has no sensitive data (no redaction needed)."""
        result = self.redact(engram)
        return result.redacted_count == 0

    def redact_text(self, text: str) -> tuple[str, int]:
        """Redact sensitive data from arbitrary text.

        Returns (redacted_text, count_of_redactions).
        """
        count = 0
        for pattern, replacement in self._compiled:
            matches = pattern.findall(text)
            if matches:
                count += len(matches)
                text = pattern.sub(replacement, text)
        return text, count
