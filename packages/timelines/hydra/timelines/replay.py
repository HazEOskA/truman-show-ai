"""Replay.

    nearest snapshot ≤ T  +  deterministic re-simulation  =  world state at T

The ledger tells the story of what happened; determinism reproduces the state. Every replay
verifies its result against the checkpoint hashes recorded during the original run, so a
divergence is an error, never a silent difference.
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.kernel.config import WorldConfig
from hydra.kernel.errors import DeterminismError
from hydra.kernel.kernelstate import KernelDomainState
from hydra.persistence.store import WorldStore
from hydra.world.builder import WorldRuntime, load_world


@dataclass(slots=True)
class ReplayReport:
    timeline_id: str
    from_tick: int
    to_tick: int
    ticks_resimulated: int
    verified_checkpoints: int
    state_hash: str


def replay_to(
    store: WorldStore,
    *,
    config: WorldConfig,
    timeline_id: str,
    tick: int,
    verify: bool = True,
) -> WorldRuntime:
    """Return a runtime whose state is exactly the world at ``tick``."""

    runtime = load_world(store, config=config, timeline_id=timeline_id, tick=tick, verify=verify)
    if runtime.state.meta.tick > tick:
        raise DeterminismError(
            f"nearest snapshot for {timeline_id} is at tick {runtime.state.meta.tick}, past the requested {tick}"
        )
    expected = dict(runtime.state.domain(KernelDomainState).checkpoints)
    # Re-simulation must not append a second copy of history to the ledger.
    runtime.kernel.sink = None
    runtime.kernel.snapshot_hook = None
    while runtime.state.meta.tick < tick:
        runtime.kernel.tick()
        if verify:
            _verify(runtime, expected)
    return runtime


def replay_report(
    store: WorldStore,
    *,
    config: WorldConfig,
    timeline_id: str,
    tick: int,
) -> ReplayReport:
    snapshot = store.nearest_snapshot(timeline_id, tick)
    if snapshot is None:
        raise FileNotFoundError(f"no snapshot for timeline {timeline_id}")
    runtime = replay_to(store, config=config, timeline_id=timeline_id, tick=tick)
    kernel_state = runtime.state.domain(KernelDomainState)
    return ReplayReport(
        timeline_id=timeline_id,
        from_tick=snapshot.tick,
        to_tick=tick,
        ticks_resimulated=tick - snapshot.tick,
        verified_checkpoints=len(kernel_state.checkpoints),
        state_hash=runtime.state.state_hash(),
    )


def _verify(runtime: WorldRuntime, expected: dict[str, str]) -> None:
    tick = runtime.state.meta.tick
    recorded = expected.get(str(tick))
    if recorded is None:
        return
    current = runtime.state.state_hash()
    if current != recorded:
        raise DeterminismError(
            f"replay diverged at tick {tick}: recorded {recorded}, replayed {current}"
        )
