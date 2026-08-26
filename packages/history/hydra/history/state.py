"""In-world history index.

The full ledger lives in the store; this domain keeps the bounded working set the world
itself needs during simulation — what recently mattered, how often topics fire, and the
chronicle an operator or a journalist agent reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


@dataclass(slots=True)
class ChronicleEntry:
    event_id: str
    tick: int
    sim_time: str
    topic: str
    action: str
    actor: str | None
    target: str | None
    importance: float
    summary: str
    causes: list[str] = field(default_factory=list)


@register_domain
@dataclass(slots=True)
class HistoryState(DomainState):
    DOMAIN: ClassVar[str] = "history"

    chronicle: list[ChronicleEntry] = field(default_factory=list)
    topic_counts: dict[str, int] = field(default_factory=dict)
    era_labels: dict[str, str] = field(default_factory=dict)
    max_chronicle: int = 400
    total_events: int = 0
