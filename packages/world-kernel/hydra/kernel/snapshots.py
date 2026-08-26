"""Snapshot capture and restore.

A snapshot is the canonical encoding of the whole world plus the identity triple
(seed, kernel version, config hash) and the state hash at capture time. Restoring verifies
the hash, so a corrupted or mismatched snapshot fails loudly instead of quietly forking
reality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import DeterminismError
from .state import WorldState
from .version import KERNEL_VERSION


@dataclass(slots=True)
class Snapshot:
    world_id: str
    timeline_id: str
    tick: int
    state_hash: str
    config_hash: str
    seed: int
    kernel_version: str = KERNEL_VERSION
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return f"snapshot_{self.tick:09d}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "timeline_id": self.timeline_id,
            "tick": self.tick,
            "state_hash": self.state_hash,
            "config_hash": self.config_hash,
            "seed": self.seed,
            "kernel_version": self.kernel_version,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Snapshot":
        return cls(
            world_id=raw["world_id"],
            timeline_id=raw["timeline_id"],
            tick=int(raw["tick"]),
            state_hash=raw["state_hash"],
            config_hash=raw["config_hash"],
            seed=int(raw["seed"]),
            kernel_version=raw.get("kernel_version", KERNEL_VERSION),
            payload=raw.get("payload", {}),
        )


def take_snapshot(state: WorldState) -> Snapshot:
    # The payload is the exact encoding (so the world round-trips bit for bit); the recorded
    # hash is the world's canonical identity hash (so it can be compared with a live run).
    payload = state.to_dict()
    return Snapshot(
        world_id=state.meta.world_id,
        timeline_id=state.meta.timeline_id,
        tick=state.meta.tick,
        state_hash=state.state_hash(),
        config_hash=state.meta.config_hash,
        seed=state.meta.seed,
        kernel_version=state.meta.kernel_version,
        payload=payload,
    )


def restore_snapshot(snapshot: Snapshot, *, verify: bool = True) -> WorldState:
    state = WorldState.from_dict(snapshot.payload)
    if verify:
        rehashed = state.state_hash()
        if rehashed != snapshot.state_hash:
            raise DeterminismError(
                f"snapshot {snapshot.name} does not round-trip: "
                f"stored {snapshot.state_hash}, rebuilt {rehashed}"
            )
        if snapshot.kernel_version != KERNEL_VERSION:
            raise DeterminismError(
                f"snapshot was written by kernel {snapshot.kernel_version}, "
                f"this kernel is {KERNEL_VERSION}"
            )
    return state
