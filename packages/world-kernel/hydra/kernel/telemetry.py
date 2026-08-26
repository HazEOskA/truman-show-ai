"""Observability counters (spec section 37)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Telemetry:
    counters: dict[str, float] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    tick_ms: float = 0.0

    def incr(self, key: str, amount: float = 1.0) -> None:
        self.counters[key] = self.counters.get(key, 0.0) + amount

    def gauge(self, key: str, value: float) -> None:
        self.gauges[key] = value

    def reset_counters(self) -> None:
        self.counters.clear()

    # Metrics measured against the wall clock describe the machine, not the world. They are
    # reported and stored, but they must never enter the hashed world state or two identical
    # runs would hash differently purely because one of them ran on a busier CPU.
    WALL_CLOCK_KEYS = ("tick_ms",)

    def snapshot(self, *, include_wall_clock: bool = True) -> dict[str, float]:
        merged: dict[str, float] = {}
        merged.update(self.gauges)
        merged.update(self.counters)
        if include_wall_clock:
            merged["tick_ms"] = self.tick_ms
        return merged
