"""System contract (rule 35.13: every subsystem has an explicit input/output contract)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .errors import ContractViolation


class Phase(enum.IntEnum):
    """Fixed intra-tick order (spec section 4)."""

    ENVIRONMENT = 1
    AGENTS = 2
    INSTITUTIONS = 3
    MARKETS = 4
    PHYSICAL = 5
    INFORMATION = 6
    SLOW = 7


@dataclass(frozen=True, slots=True)
class SystemSpec:
    name: str
    phase: Phase
    cadence_ticks: int = 1
    priority: int = 100
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    description: str = ""

    def with_cadence(self, cadence_ticks: int) -> "SystemSpec":
        """Composition root override — cadences are configuration, not constants."""

        import dataclasses

        return dataclasses.replace(self, cadence_ticks=max(0, cadence_ticks))

    def runs_at(self, tick: int) -> bool:
        if self.cadence_ticks <= 0:
            return False        # event-driven only
        return tick % self.cadence_ticks == 0


@runtime_checkable
class System(Protocol):
    spec: SystemSpec

    def step(self, ctx) -> None:  # noqa: ANN001 - TickContext, avoided for import cycles
        ...


class SystemRegistry:
    """Ordered, validated collection of systems."""

    __slots__ = ("_systems", "_by_name")

    def __init__(self) -> None:
        self._systems: list[System] = []
        self._by_name: dict[str, System] = {}

    def register(self, system: System) -> System:
        spec = system.spec
        if spec.name in self._by_name:
            raise ContractViolation(f"system {spec.name!r} registered twice")
        self._by_name[spec.name] = system
        self._systems.append(system)
        self._systems.sort(key=lambda s: (int(s.spec.phase), s.spec.priority, s.spec.name))
        return system

    def get(self, name: str) -> System:
        return self._by_name[name]

    def all(self) -> list[System]:
        return list(self._systems)

    def due(self, tick: int, skip: frozenset[str] = frozenset()) -> list[System]:
        return [s for s in self._systems if s.spec.runs_at(tick) and s.spec.name not in skip]

    def event_driven(self) -> list[System]:
        return [s for s in self._systems if s.spec.cadence_ticks <= 0 or s.spec.consumes]

    def contracts(self) -> list[SystemSpec]:
        return [s.spec for s in self._systems]


@dataclass(slots=True)
class SystemHealth:
    """Failure bookkeeping for recovery (a crashing system must not kill the world)."""

    failures: int = 0
    last_error: str = ""
    last_failure_tick: int = -1
    quarantined: bool = False
    history: list[str] = field(default_factory=list)
