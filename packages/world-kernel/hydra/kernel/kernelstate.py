"""Kernel's own domain state.

Timers, quarantine flags and checkpoint hashes are world state: they must survive snapshots
and travel with a fork, otherwise a replay diverges from the original run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from .state import DomainState, register_domain
from .systems import SystemHealth


@dataclass(slots=True)
class Timer:
    fire_tick: int
    topic: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    actor: str | None = None
    target: str | None = None
    importance: float = 0.5
    repeat_ticks: int = 0


@register_domain
@dataclass(slots=True)
class KernelDomainState(DomainState):
    DOMAIN: ClassVar[str] = "kernel"

    timers: list[Timer] = field(default_factory=list)
    health: dict[str, SystemHealth] = field(default_factory=dict)
    checkpoints: dict[str, str] = field(default_factory=dict)   # str(tick) -> state hash
    snapshot_ticks: list[int] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    counters: dict[str, float] = field(default_factory=dict)
    rejected_actions: int = 0
    executed_actions: int = 0
    topic_seen: dict[str, int] = field(default_factory=dict)   # novelty memory (see ImportanceScorer)
