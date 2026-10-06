from __future__ import annotations
"""State of live (webcam / screen-share) sessions, kept in memory.

The browser sends ~1 frame per second. Each frame gets an immediate (smoothed)
score for the screen; every LIVE_WINDOW_FRAMES frames one Analysis is stored.
Note: in-memory state means the server must run as ONE process (threads are fine).
"""
import threading
import time
from dataclasses import dataclass, field

from .pipeline import WindowSummary
from .risk import Smoother


@dataclass
class LiveState:
    meeting_id: int
    reference_embedding: object
    smoother: Smoother
    started: float = field(default_factory=time.perf_counter)
    window: WindowSummary = field(default_factory=WindowSummary)
    window_started: float = field(default_factory=time.perf_counter)
    frames_total: int = 0
    first_score_ms: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_sessions: dict[int, LiveState] = {}
_registry_lock = threading.Lock()


def start(meeting_id, reference_embedding, smoothing_window):
    with _registry_lock:
        _sessions[meeting_id] = LiveState(meeting_id, reference_embedding, Smoother(smoothing_window))
        return _sessions[meeting_id]


def get(meeting_id):
    return _sessions.get(meeting_id)


def stop(meeting_id):
    with _registry_lock:
        return _sessions.pop(meeting_id, None)


def active_count():
    return len(_sessions)
