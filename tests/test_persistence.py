"""Persistence: snapshots, the ledger, and the rule that a sealed past cannot be rewritten."""

from __future__ import annotations

import pytest

from hydra.events.model import Event, Topics
from hydra.kernel.clock import TICKS_PER_DAY
from hydra.kernel.errors import DeterminismError, SealedTimelineError
from hydra.kernel.snapshots import restore_snapshot, take_snapshot
from hydra.persistence.filestore import FileStore
from hydra.persistence.store import ControlState, TimelineRecord, WorldRecord
from hydra.world import create_world

from conftest import small_config


def test_snapshot_round_trips_a_whole_world(world):
    world.kernel.run(60)
    snapshot = take_snapshot(world.state)
    restored = restore_snapshot(snapshot)
    assert restored.state_hash() == world.state.state_hash()
    assert restored.meta.tick == world.state.meta.tick


def test_a_corrupted_snapshot_is_rejected(world):
    snapshot = take_snapshot(world.state)
    snapshot.state_hash = "0" * 32
    with pytest.raises(DeterminismError):
        restore_snapshot(snapshot)


def test_filestore_round_trips_worlds_timelines_snapshots_and_events(tmp_path):
    store = FileStore(tmp_path)
    store.put_world(WorldRecord(world_id="w1", name="Hydra", seed=1, config_hash="c", kernel_version="0.1.0",
                                root_timeline_id="tl_zero"))
    store.put_timeline(TimelineRecord(timeline_id="tl_zero", world_id="w1", seed=1, label="Timeline Zero"))
    assert store.get_world("w1").name == "Hydra"
    assert [t.timeline_id for t in store.list_timelines("w1")] == ["tl_zero"]

    events = [
        Event(event_id=f"evt_{i:03d}", tick=i, topic=Topics.COMPANY_LAYOFF, action="laid_off_workers",
              actor="company_0001", importance=0.5 + i / 100)
        for i in range(5)
    ]
    assert store.append_events("tl_zero", events) == 5
    assert store.count_events("tl_zero") == 5
    found = store.read_events("tl_zero", topics=("company.*",), limit=3)
    assert len(found) == 3 and found[0].tick > found[-1].tick, "newest first by default"
    assert store.get_event("tl_zero", "evt_002").actor == "company_0001"

    store.put_control(ControlState(world_id="w1", timeline_id="tl_zero", mode="running", speed=8.0))
    assert store.get_control("w1", "tl_zero").mode == "running"

    store.write_telemetry("tl_zero", 6, {"cpi": 1.02})
    assert store.read_telemetry("tl_zero")[-1]["metrics"]["cpi"] == 1.02


def test_a_sealed_timeline_cannot_have_its_past_rewritten(tmp_path):
    store = FileStore(tmp_path)
    store.put_world(WorldRecord(world_id="w1", name="Hydra", seed=1, config_hash="c",
                                kernel_version="0.1.0", root_timeline_id="tl_zero"))
    store.put_timeline(TimelineRecord(timeline_id="tl_zero", world_id="w1", seed=1, sealed=True, head_tick=0))
    store.append_events("tl_zero", [Event(event_id="evt_100", tick=100, topic="x", action="y")])

    with pytest.raises(SealedTimelineError):
        store.append_events("tl_zero", [Event(event_id="evt_050", tick=50, topic="x", action="y")])

    # Appending to the future is always allowed: history grows forwards.
    assert store.append_events("tl_zero", [Event(event_id="evt_101", tick=101, topic="x", action="y")]) == 1


def test_live_state_and_snapshots_are_separate(tmp_path):
    store = FileStore(tmp_path)
    runtime = create_world(small_config(), seed=31, world_id="w_live", store=store)
    runtime.kernel.run(20)
    store.write_live(take_snapshot(runtime.state))

    assert store.list_snapshot_ticks("tl_zero") == [0], "genesis snapshot only"
    live = store.read_live("tl_zero")
    assert live is not None and live.tick == 20
    assert store.nearest_snapshot("tl_zero", 20).tick == 0


def test_ledger_writes_important_events_only(tmp_path):
    store = FileStore(tmp_path)
    runtime = create_world(small_config(), seed=32, world_id="w_ledger", store=store)
    runtime.kernel.run(TICKS_PER_DAY // 2)
    runtime.ledger.flush()

    events = store.read_events("tl_zero", limit=500)
    assert events, "a running world writes history"
    threshold = runtime.config.kernel.ledger_importance_threshold
    assert all(event.importance >= threshold for event in events)
