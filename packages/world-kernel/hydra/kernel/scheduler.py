"""Tick and event scheduling."""

from __future__ import annotations

from typing import Any

from .kernelstate import KernelDomainState, Timer
from .systems import System, SystemRegistry


class Scheduler:
    """Decides what runs this tick and owns the timer queue.

    Timers live in world state, so ``schedule_at`` survives snapshot/restore and forking.
    """

    __slots__ = ("registry",)

    def __init__(self, registry: SystemRegistry) -> None:
        self.registry = registry

    def due_systems(self, tick: int, kstate: KernelDomainState) -> list[System]:
        skip = frozenset(name for name, h in kstate.health.items() if h.quarantined)
        return self.registry.due(tick, skip)

    @staticmethod
    def schedule_at(
        kstate: KernelDomainState,
        fire_tick: int,
        topic: str,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        actor: str | None = None,
        target: str | None = None,
        importance: float = 0.5,
        repeat_ticks: int = 0,
    ) -> Timer:
        timer = Timer(
            fire_tick=fire_tick,
            topic=topic,
            action=action,
            payload=payload or {},
            actor=actor,
            target=target,
            importance=importance,
            repeat_ticks=repeat_ticks,
        )
        kstate.timers.append(timer)
        # Keep the queue ordered so firing order is deterministic regardless of insertion order.
        kstate.timers.sort(key=lambda t: (t.fire_tick, t.topic, t.action, t.actor or "", t.target or ""))
        return timer

    @staticmethod
    def pop_due_timers(kstate: KernelDomainState, tick: int) -> list[Timer]:
        due: list[Timer] = []
        remaining: list[Timer] = []
        for timer in kstate.timers:
            if timer.fire_tick <= tick:
                due.append(timer)
                if timer.repeat_ticks > 0:
                    remaining.append(
                        Timer(
                            fire_tick=timer.fire_tick + timer.repeat_ticks,
                            topic=timer.topic,
                            action=timer.action,
                            payload=dict(timer.payload),
                            actor=timer.actor,
                            target=timer.target,
                            importance=timer.importance,
                            repeat_ticks=timer.repeat_ticks,
                        )
                    )
            else:
                remaining.append(timer)
        remaining.sort(key=lambda t: (t.fire_tick, t.topic, t.action, t.actor or "", t.target or ""))
        kstate.timers = remaining
        return due
