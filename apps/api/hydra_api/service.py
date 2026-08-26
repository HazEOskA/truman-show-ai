"""World service: the API's view of the simulation.

The worker owns the running world; the API owns reading it and expressing operator intent.
They meet at the store: state and telemetry flow one way, control flows the other. That split
is what makes the Observatory read-first — nothing an operator clicks can reach into a
running tick and change it mid-flight.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any

from hydra.kernel.config import WorldConfig
from hydra.kernel.snapshots import Snapshot, restore_snapshot
from hydra.kernel.state import WorldState
from hydra.persistence.filestore import FileStore
from hydra.persistence.store import ControlState, TimelineRecord, WorldRecord, WorldStore
from hydra.timelines.fork import fork_timeline, timeline_tree
from hydra.timelines.replay import replay_report, replay_to
from hydra.world import create_world


def build_store() -> WorldStore:
    """Postgres when configured, filesystem otherwise. Both are first-class."""

    dsn = os.environ.get("HYDRA_DATABASE_URL", "").strip()
    if dsn:
        from hydra.persistence.postgres import PostgresStore

        return PostgresStore(dsn)
    return FileStore(os.environ.get("HYDRA_DATA_DIR", "./data"))


@dataclass(slots=True)
class CachedState:
    tick: int
    state: WorldState


class WorldService:
    def __init__(self, store: WorldStore | None = None) -> None:
        self.store = store or build_store()
        self._cache: dict[str, CachedState] = {}
        self._lock = threading.Lock()

    # -- lifecycle ----------------------------------------------------------------
    def create_world(
        self,
        *,
        seed: int,
        world_id: str = "",
        name: str = "Hydra World",
        residents: int | None = None,
        persistent_agents: int | None = None,
        companies: int | None = None,
    ) -> dict[str, Any]:
        config = WorldConfig(world_name=name)
        if residents:
            config.population.total_residents = residents
            config.population.lightweight_agents = max(400, min(config.population.lightweight_agents, residents // 8))
        if persistent_agents:
            config.population.persistent_agents = persistent_agents
        if companies:
            config.economy.company_count = companies

        world_id = world_id or f"world_{seed}"
        if self.store.get_world(world_id) is not None:
            raise ValueError(f"world {world_id} already exists")

        runtime = create_world(config, seed=seed, world_id=world_id, store=self.store)
        self.store.write_live(runtime.kernel.snapshot())
        self.store.put_control(
            ControlState(world_id=world_id, timeline_id="tl_zero", mode="paused", speed=4.0)
        )
        with self._lock:
            self._cache["tl_zero"] = CachedState(tick=runtime.state.meta.tick, state=runtime.state)
        return {
            "world_id": world_id,
            "timeline_id": "tl_zero",
            "seed": seed,
            "config_hash": config.config_hash(),
            "state_hash": runtime.state.state_hash(),
            "population": config.population.total_residents,
        }

    def config_for(self, world_id: str) -> WorldConfig:
        record = self.store.get_world(world_id)
        config = WorldConfig()
        if record is None:
            return config
        from hydra.kernel.serialization import decode

        try:
            return decode(WorldConfig, record.config)
        except Exception:  # noqa: BLE001 - a config we cannot decode must not break reads
            return config

    # -- reads --------------------------------------------------------------------
    def worlds(self) -> list[WorldRecord]:
        return self.store.list_worlds()

    def timelines(self, world_id: str) -> list[TimelineRecord]:
        return self.store.list_timelines(world_id)

    def timeline_tree(self, world_id: str) -> dict[str, list[str]]:
        return timeline_tree(self.store, world_id)

    def state(self, timeline_id: str) -> WorldState:
        record = self.store.get_timeline(timeline_id)
        head = record.head_tick if record else -1
        with self._lock:
            cached = self._cache.get(timeline_id)
            if cached is not None and cached.tick >= head:
                return cached.state
        snapshot = self.store.read_live(timeline_id) or self.store.nearest_snapshot(timeline_id, 10**12)
        if snapshot is None:
            raise FileNotFoundError(f"timeline {timeline_id} has no state yet")
        state = restore_snapshot(snapshot, verify=False)
        with self._lock:
            self._cache[timeline_id] = CachedState(tick=state.meta.tick, state=state)
        return state

    def invalidate(self, timeline_id: str) -> None:
        with self._lock:
            self._cache.pop(timeline_id, None)

    def telemetry(self, timeline_id: str, limit: int = 240) -> list[dict[str, Any]]:
        return self.store.read_telemetry(timeline_id, limit)

    def events(self, timeline_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        from hydra.kernel.serialization import encode

        return [encode(e) for e in self.store.read_events(timeline_id, **kwargs)]

    def causal_chain(self, timeline_id: str, event_id: str) -> dict[str, Any]:
        from hydra.history.causal import CausalGraph
        from hydra.kernel.serialization import encode

        events = self.store.read_events(timeline_id, limit=6000, newest_first=False)
        graph = CausalGraph(events)
        target = graph.by_id.get(event_id)
        if target is None:
            return {"event": None, "chain": [], "consequences": []}
        return {
            "event": encode(target),
            "chain": [
                {"depth": node.depth, "event": encode(node.event)} for node in graph.why(event_id)
            ],
            "consequences": [
                {"depth": node.depth, "event": encode(node.event)} for node in graph.consequences(event_id)
            ],
        }

    # -- control ------------------------------------------------------------------
    def control(self, world_id: str, timeline_id: str) -> ControlState:
        return self.store.get_control(world_id, timeline_id) or ControlState(
            world_id=world_id, timeline_id=timeline_id
        )

    def set_control(
        self,
        world_id: str,
        timeline_id: str,
        *,
        mode: str | None = None,
        speed: float | None = None,
        step_ticks: int | None = None,
        target_tick: int | None = None,
        scenario: str | None = None,
        note: str | None = None,
    ) -> ControlState:
        control = self.control(world_id, timeline_id)
        control.world_id = world_id
        control.timeline_id = timeline_id
        if mode is not None:
            control.mode = mode
        if speed is not None:
            control.speed = speed
        if step_ticks is not None:
            control.step_ticks = step_ticks
        if target_tick is not None:
            control.target_tick = target_tick
        if scenario is not None:
            control.scenario = scenario
        if note is not None:
            control.note = note
        self.store.put_control(control)
        return control

    # -- time machine -------------------------------------------------------------
    def fork(
        self,
        world_id: str,
        timeline_id: str,
        *,
        fork_tick: int,
        label: str = "",
        divergence_salt: str = "",
    ) -> dict[str, Any]:
        result = fork_timeline(
            self.store,
            config=self.config_for(world_id),
            world_id=world_id,
            parent_timeline_id=timeline_id,
            fork_tick=fork_tick,
            label=label,
            divergence_salt=divergence_salt,
        )
        snapshot = self.store.read_snapshot(result.timeline.timeline_id, fork_tick)
        if snapshot is not None:
            self.store.write_live(snapshot)
        self.store.put_control(
            ControlState(
                world_id=world_id,
                timeline_id=result.timeline.timeline_id,
                mode="paused",
                speed=4.0,
            )
        )
        return {
            "timeline_id": result.timeline.timeline_id,
            "parent_timeline_id": timeline_id,
            "fork_tick": result.tick,
            "state_hash": result.state_hash,
            "label": result.timeline.label,
            "seed_lineage": result.timeline.seed_lineage,
        }

    def replay(self, world_id: str, timeline_id: str, tick: int) -> dict[str, Any]:
        report = replay_report(
            self.store, config=self.config_for(world_id), timeline_id=timeline_id, tick=tick
        )
        return {
            "timeline_id": report.timeline_id,
            "from_tick": report.from_tick,
            "to_tick": report.to_tick,
            "ticks_resimulated": report.ticks_resimulated,
            "verified_checkpoints": report.verified_checkpoints,
            "state_hash": report.state_hash,
        }

    def state_at(self, world_id: str, timeline_id: str, tick: int) -> WorldState:
        runtime = replay_to(
            self.store, config=self.config_for(world_id), timeline_id=timeline_id, tick=tick
        )
        return runtime.state

    def snapshots(self, timeline_id: str) -> list[int]:
        return self.store.list_snapshot_ticks(timeline_id)
