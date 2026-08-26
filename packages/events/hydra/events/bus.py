"""Event bus.

Delivery is subscription-based, never global polling: a system receives only the topics it
declared. Ordering is deterministic — subscribers are called in registration order, and
events are processed in emission order — so a replay produces byte-identical results.

``EventTransport`` is the seam for NATS/Kafka/PubSub later; the MVP ships one real
in-process implementation.
"""

from __future__ import annotations

from collections import deque
from typing import Callable, Iterable, Protocol

from .model import Event

Handler = Callable[[Event], None]


class EventTransport(Protocol):
    """Contract every transport must satisfy."""

    def publish(self, event: Event) -> None: ...
    def subscribe(self, pattern: str, handler: Handler, subscriber: str) -> None: ...
    def drain(self) -> list[Event]: ...


class InProcessTransport:
    """Single-process transport used by the MVP worker."""

    __slots__ = ("_subscriptions", "_pending", "_delivered")

    def __init__(self) -> None:
        self._subscriptions: list[tuple[str, Handler, str]] = []
        self._pending: deque[Event] = deque()
        self._delivered: list[Event] = []

    def subscribe(self, pattern: str, handler: Handler, subscriber: str = "") -> None:
        self._subscriptions.append((pattern, handler, subscriber))

    def publish(self, event: Event) -> None:
        self._pending.append(event)

    def drain(self) -> list[Event]:
        """Deliver everything pending, including events emitted by handlers."""

        delivered: list[Event] = []
        guard = 0
        while self._pending:
            guard += 1
            if guard > 100_000:
                raise RuntimeError("event storm: handlers are emitting without converging")
            event = self._pending.popleft()
            for pattern, handler, _ in self._subscriptions:
                if _matches(pattern, event.topic):
                    handler(event)
            delivered.append(event)
        self._delivered.extend(delivered)
        return delivered

    def subscribers(self) -> list[tuple[str, str]]:
        return [(pattern, name) for pattern, _, name in self._subscriptions]


def _matches(pattern: str, topic: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith("*"):
        return topic.startswith(pattern[:-1])
    return pattern == topic


class EventBus:
    """Thin façade the kernel hands to systems.

    Systems never touch the transport directly, which keeps the swap to a networked
    transport a one-line change in the composition root.
    """

    __slots__ = ("_transport", "history_limit", "_recent")

    def __init__(self, transport: EventTransport | None = None, history_limit: int = 512) -> None:
        self._transport = transport or InProcessTransport()
        self.history_limit = history_limit
        self._recent: deque[Event] = deque(maxlen=history_limit)

    @property
    def transport(self) -> EventTransport:
        return self._transport

    def subscribe(self, patterns: Iterable[str], handler: Handler, subscriber: str = "") -> None:
        for pattern in patterns:
            self._transport.subscribe(pattern, handler, subscriber)

    def publish(self, event: Event) -> None:
        self._transport.publish(event)

    def drain(self) -> list[Event]:
        delivered = self._transport.drain()
        self._recent.extend(delivered)
        return delivered

    def recent(self, limit: int = 50) -> list[Event]:
        events = list(self._recent)
        return events[-limit:]
