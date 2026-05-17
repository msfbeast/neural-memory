"""Capture module — auto-capture events into engrams."""

from src.capture.event_loop import EventLoop
from src.capture.filters import Filter, CaptureDecision, EventCategory
from src.capture.extractor import Extractor, Engram

__all__ = ["EventLoop", "Filter", "CaptureDecision", "EventCategory", "Extractor", "Engram"]
