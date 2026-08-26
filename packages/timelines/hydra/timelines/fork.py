"""Timeline forks (spec section 24).

Timeline Zero is immutable. Experiments happen on branches: a fork copies the world state at
a chosen tick, records its lineage, and runs from there with its own RNG stream. Two forks of
the same tick with the same salt produce the same history; with different salts they diverge
the way two runs of the same experiment do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from hydra.kernel.rng import derive_seed
from hydra.kernel.snapshots import take_snapshot
from hydra.kernel.state import WorldPhase
from hydra.persistence.store import TimelineRecord, WorldStore

from .replay import replay_to


@dataclass(slots=True)
class ForkResult:
    timeline: TimelineRecord
    tick: int
    state_hash: str


def next_timeline_id(store: WorldStore, world_id: str) -> str:
    existing = {t.timeline_id for t in store.list_timelines(world_id)}
    index = 1
    while f"tl_{index:03d}" in existing:
        index += 1
    return f"tl_{index:03d}"


def fork_timeline(
    store: WorldStore,
    *,
    config,
    world_id: str,
    parent_timeline_id: str,
    fork_tick: int,
    label: str = "",
    divergence_salt: str = "",
    timeline_id: str | None = None,
) -> ForkResult:
    parent = store.get_timeline(parent_timeline_id)
    if parent is None:
        raise ValueError(f"unknown timeline {parent_timeline_id}")
    if fork_tick > parent.head_tick:
        raise ValueError(
            f"cannot fork {parent_timeline_id} at tick {fork_tick}: it has only reached {parent.head_tick}"
        )

    runtime = replay_to(store, config=config, timeline_id=parent_timeline_id, tick=fork_tick)
    state = runtime.state
    new_id = timeline_id or next_timeline_id(store, world_id)

    # The child's randomness descends from the parent's, so lineage is auditable and a fork
    # with the same salt is reproducible.
    child_seed = derive_seed(state.meta.seed, "fork", new_id, fork_tick, divergence_salt)
    state.meta.timeline_id = new_id
    state.meta.parent_timeline_id = parent_timeline_id
    state.meta.fork_tick = fork_tick
    state.meta.seed = child_seed
    state.meta.seed_lineage = list(parent.seed_lineage) + [f"{parent_timeline_id}@{fork_tick}:{child_seed}"]
    state.meta.phase = WorldPhase.SEALED

    record = TimelineRecord(
        timeline_id=new_id,
        world_id=world_id,
        parent_timeline_id=parent_timeline_id,
        fork_tick=fork_tick,
        seed=child_seed,
        seed_lineage=list(state.meta.seed_lineage),
        label=label or f"fork of {parent_timeline_id} @ {fork_tick}",
        sealed=False,
        head_tick=fork_tick,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        divergence_note=divergence_salt,
    )
    store.put_timeline(record)
    snapshot = take_snapshot(state)
    store.write_snapshot(snapshot)
    return ForkResult(timeline=record, tick=fork_tick, state_hash=snapshot.state_hash)


def timeline_tree(store: WorldStore, world_id: str) -> dict[str, list[str]]:
    """Parent → children map, for the Observatory's timeline view."""

    tree: dict[str, list[str]] = {}
    for record in store.list_timelines(world_id):
        tree.setdefault(record.parent_timeline_id or "", []).append(record.timeline_id)
    for children in tree.values():
        children.sort()
    return tree
