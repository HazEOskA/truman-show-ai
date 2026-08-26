"""Time machine: replay, forks and lineage (spec sections 23–24)."""

from __future__ import annotations

import pytest

from hydra.kernel.clock import TICKS_PER_DAY
from hydra.kernel.kernelstate import KernelDomainState
from hydra.kernel.snapshots import take_snapshot
from hydra.persistence.filestore import FileStore
from hydra.timelines.fork import fork_timeline, timeline_tree
from hydra.timelines.replay import replay_report, replay_to
from hydra.world import create_world
from hydra.world.scenarios import run_scenario

from conftest import small_config


def domains_hash(state) -> str:
    """Hash the world without its identity card (see ``WorldState.domains_hash``)."""

    return state.domains_hash()


def _running_world(tmp_path, seed: int = 71, ticks: int = 200):
    store = FileStore(tmp_path)
    config = small_config()
    config.kernel.snapshot_interval = 100
    runtime = create_world(config, seed=seed, world_id="w_time", store=store)
    runtime.kernel.run(ticks)
    runtime.ledger.flush()
    store.write_live(take_snapshot(runtime.state))
    return store, config, runtime


def test_replay_reproduces_the_state_at_a_tick(tmp_path):
    store, config, runtime = _running_world(tmp_path, ticks=150)
    # Same world id on purpose: a checkpoint hash is the identity of a specific world, so
    # replaying "the same world" means the same name as well as the same seed.
    original = create_world(config, seed=71, world_id="w_time")
    original.kernel.run(150)

    replayed = replay_to(store, config=config, timeline_id="tl_zero", tick=150)
    assert replayed.state.meta.tick == 150
    assert domains_hash(replayed.state) == domains_hash(original.state)


def test_replay_verifies_against_recorded_checkpoints(tmp_path):
    store, config, runtime = _running_world(tmp_path, ticks=TICKS_PER_DAY)
    report = replay_report(store, config=config, timeline_id="tl_zero", tick=TICKS_PER_DAY)
    assert report.to_tick == TICKS_PER_DAY
    assert report.ticks_resimulated >= 0
    assert report.state_hash == runtime.state.state_hash()
    assert report.verified_checkpoints > 0


def test_replay_does_not_rewrite_history(tmp_path):
    store, config, _ = _running_world(tmp_path, ticks=150)
    before = store.count_events("tl_zero")
    replay_to(store, config=config, timeline_id="tl_zero", tick=150)
    assert store.count_events("tl_zero") == before, "a replay must not append to the ledger"


def test_fork_creates_an_independent_timeline_with_lineage(tmp_path):
    store, config, _ = _running_world(tmp_path, ticks=150)
    result = fork_timeline(
        store, config=config, world_id="w_time", parent_timeline_id="tl_zero",
        fork_tick=100, label="experiment A", divergence_salt="A",
    )
    record = store.get_timeline(result.timeline.timeline_id)
    assert record.parent_timeline_id == "tl_zero"
    assert record.fork_tick == 100
    assert record.seed_lineage and "tl_zero@100" in record.seed_lineage[-1]
    assert store.read_snapshot(record.timeline_id, 100) is not None

    tree = timeline_tree(store, "w_time")
    assert record.timeline_id in tree[""] or record.timeline_id in tree.get("tl_zero", [])


def test_two_forks_of_the_same_tick_diverge_and_the_parent_is_untouched(tmp_path):
    store, config, parent = _running_world(tmp_path, ticks=150)
    parent_hash_before = parent.state.state_hash()

    a = fork_timeline(store, config=config, world_id="w_time", parent_timeline_id="tl_zero",
                      fork_tick=100, label="A", divergence_salt="A")
    b = fork_timeline(store, config=config, world_id="w_time", parent_timeline_id="tl_zero",
                      fork_tick=100, label="B", divergence_salt="B")
    from hydra.kernel.snapshots import restore_snapshot

    snap_a = restore_snapshot(store.read_snapshot(a.timeline.timeline_id, 100), verify=False)
    snap_b = restore_snapshot(store.read_snapshot(b.timeline.timeline_id, 100), verify=False)
    assert domains_hash(snap_a) == domains_hash(snap_b), "both forks start from the same world"

    from hydra.world.builder import load_world

    world_a = load_world(store, config=config, timeline_id=a.timeline.timeline_id, tick=100)
    world_b = load_world(store, config=config, timeline_id=b.timeline.timeline_id, tick=100)
    run_scenario(world_a, "plant_failure", loss=0.6)
    world_a.kernel.run(TICKS_PER_DAY)
    world_b.kernel.run(TICKS_PER_DAY)

    assert domains_hash(world_a.state) != domains_hash(world_b.state), "different histories from here on"
    assert parent.state.state_hash() == parent_hash_before, "Timeline Zero is untouched by its forks"


def test_forking_past_the_head_is_refused(tmp_path):
    store, config, _ = _running_world(tmp_path, ticks=150)
    with pytest.raises(ValueError):
        fork_timeline(store, config=config, world_id="w_time", parent_timeline_id="tl_zero", fork_tick=10_000)


def test_a_fork_carries_its_own_random_stream(tmp_path):
    store, config, _ = _running_world(tmp_path, ticks=120)
    fork = fork_timeline(store, config=config, world_id="w_time", parent_timeline_id="tl_zero",
                         fork_tick=100, divergence_salt="salted")
    parent = store.get_timeline("tl_zero")
    assert fork.timeline.seed != parent.seed
    assert len(fork.timeline.seed_lineage) > len(parent.seed_lineage)
