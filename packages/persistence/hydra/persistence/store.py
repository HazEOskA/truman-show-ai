"""Storage contract.

Two real backends implement this: :mod:`hydra.persistence.filestore` (default, no services)
and :mod:`hydra.persistence.postgres` (docker compose). Both enforce the same rule that makes
Timeline Zero trustworthy: **the past is append-only**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from hydra.events.model import Event
from hydra.kernel.snapshots import Snapshot


@dataclass(slots=True)
class WorldRecord:
    world_id: str
    name: str
    seed: int
    config_hash: str
    kernel_version: str
    config: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    root_timeline_id: str = ""


@dataclass(slots=True)
class TimelineRecord:
    timeline_id: str
    world_id: str
    parent_timeline_id: str | None = None
    fork_tick: int | None = None
    seed: int = 0
    seed_lineage: list[str] = field(default_factory=list)
    label: str = ""
    sealed: bool = False
    head_tick: int = 0
    created_at: str = ""
    divergence_note: str = ""


@dataclass(slots=True)
class ControlState:
    """Operator intent, read by the worker at every tick boundary."""

    world_id: str
    timeline_id: str
    mode: str = "paused"           # running | paused | stopped
    speed: float = 1.0             # ticks per real second, 0 = as fast as possible
    target_tick: int | None = None
    step_ticks: int = 0
    updated_at: str = ""
    scenario: str = ""
    note: str = ""


class WorldStore(Protocol):
    # -- worlds -------------------------------------------------------------------
    def put_world(self, record: WorldRecord) -> None: ...
    def get_world(self, world_id: str) -> WorldRecord | None: ...
    def list_worlds(self) -> list[WorldRecord]: ...

    # -- timelines ----------------------------------------------------------------
    def put_timeline(self, record: TimelineRecord) -> None: ...
    def get_timeline(self, timeline_id: str) -> TimelineRecord | None: ...
    def list_timelines(self, world_id: str) -> list[TimelineRecord]: ...

    # -- snapshots ----------------------------------------------------------------
    def write_snapshot(self, snapshot: Snapshot) -> None: ...
    def read_snapshot(self, timeline_id: str, tick: int) -> Snapshot | None: ...
    def nearest_snapshot(self, timeline_id: str, tick: int) -> Snapshot | None: ...
    def list_snapshot_ticks(self, timeline_id: str) -> list[int]: ...
    def write_live(self, snapshot: Snapshot) -> None: ...
    def read_live(self, timeline_id: str) -> Snapshot | None: ...

    # -- events -------------------------------------------------------------------
    def append_events(self, timeline_id: str, events: Iterable[Event]) -> int: ...
    def read_events(
        self,
        timeline_id: str,
        *,
        start_tick: int = 0,
        end_tick: int | None = None,
        topics: tuple[str, ...] = (),
        actor: str | None = None,
        min_importance: float = 0.0,
        limit: int = 200,
        newest_first: bool = True,
    ) -> list[Event]: ...
    def get_event(self, timeline_id: str, event_id: str) -> Event | None: ...
    def count_events(self, timeline_id: str) -> int: ...

    # -- telemetry & control ------------------------------------------------------
    def write_telemetry(self, timeline_id: str, tick: int, metrics: dict[str, float]) -> None: ...
    def read_telemetry(self, timeline_id: str, limit: int = 200) -> list[dict[str, Any]]: ...
    def put_control(self, control: ControlState) -> None: ...
    def get_control(self, world_id: str, timeline_id: str) -> ControlState | None: ...
