"""Causal graph over the event ledger.

The point of the ledger is being able to ask *why*: "why did the war start" must return a
chain the world actually produced, not a story a model invented afterwards. Edges come from
``Event.causes``, which systems set whenever they act on another event.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hydra.events.model import Event


@dataclass(slots=True)
class CausalNode:
    event: Event
    depth: int
    causes: list[str] = field(default_factory=list)


class CausalGraph:
    """Read model built from a slice of ledger events."""

    def __init__(self, events: list[Event]) -> None:
        self.by_id: dict[str, Event] = {e.event_id: e for e in events}
        self.forward: dict[str, list[str]] = {}
        for event in events:
            for cause in event.causes:
                self.forward.setdefault(cause, []).append(event.event_id)

    def why(self, event_id: str, max_depth: int = 12, max_nodes: int = 60) -> list[CausalNode]:
        """Ancestor chain, root cause first."""

        root = self.by_id.get(event_id)
        if root is None:
            return []
        seen: set[str] = set()
        nodes: list[CausalNode] = []
        frontier: list[tuple[str, int]] = [(event_id, 0)]
        while frontier and len(nodes) < max_nodes:
            current_id, depth = frontier.pop(0)
            if current_id in seen or depth > max_depth:
                continue
            seen.add(current_id)
            event = self.by_id.get(current_id)
            if event is None:
                continue
            nodes.append(CausalNode(event=event, depth=depth, causes=list(event.causes)))
            for cause in event.causes:
                frontier.append((cause, depth + 1))
        nodes.sort(key=lambda n: (-n.depth, n.event.tick, n.event.event_id))
        return nodes

    def consequences(self, event_id: str, max_depth: int = 6, max_nodes: int = 80) -> list[CausalNode]:
        seen: set[str] = set()
        nodes: list[CausalNode] = []
        frontier: list[tuple[str, int]] = [(event_id, 0)]
        while frontier and len(nodes) < max_nodes:
            current_id, depth = frontier.pop(0)
            if current_id in seen or depth > max_depth:
                continue
            seen.add(current_id)
            event = self.by_id.get(current_id)
            if event is not None and depth > 0:
                nodes.append(CausalNode(event=event, depth=depth))
            for child in self.forward.get(current_id, []):
                frontier.append((child, depth + 1))
        nodes.sort(key=lambda n: (n.event.tick, n.event.event_id))
        return nodes

    def chain(self, event_id: str) -> list[str]:
        """Human-readable causal chain: ``drought → food shortage → inflation → …``."""

        return [f"{n.event.sim_time} {n.event.action}" for n in self.why(event_id)]

    def roots(self, event_id: str) -> list[Event]:
        return [n.event for n in self.why(event_id) if not n.causes]
