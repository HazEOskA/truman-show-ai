"""Immutable history ledger.

Every event above the importance threshold lands here exactly once, in tick order. The
ledger is the world's memory of itself: replay, causal analysis and the Observatory's event
feed all read from it. It is append-only by contract, enforced by the store.
"""

from __future__ import annotations

from hydra.events.model import Event
from hydra.persistence.store import WorldStore


class Ledger:
    """Buffered :class:`~hydra.kernel.context.EventSink` implementation."""

    __slots__ = ("store", "timeline_id", "_buffer", "batch_size", "written")

    def __init__(self, store: WorldStore, timeline_id: str, batch_size: int = 256) -> None:
        self.store = store
        self.timeline_id = timeline_id
        self.batch_size = batch_size
        self._buffer: list[Event] = []
        self.written = 0

    def append(self, event: Event) -> None:
        self._buffer.append(event)
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> int:
        if not self._buffer:
            return 0
        count = self.store.append_events(self.timeline_id, self._buffer)
        self.written += count
        self._buffer.clear()
        return count

    def pending(self) -> int:
        return len(self._buffer)


class NullLedger:
    """Used by in-memory runs (tests, determinism checks) that keep no history."""

    __slots__ = ("events",)

    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def flush(self) -> int:
        return 0
