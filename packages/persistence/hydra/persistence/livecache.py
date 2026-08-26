"""Redis cache for the live world state.

The Observatory asks for the current world several times a second; the current world is a
multi-megabyte canonical snapshot. Fetching and decompressing that out of Postgres on every
request is the one part of the read path that genuinely needs a cache, so that is exactly what
Redis is here for — nothing else.

Everything is write-through: the store remains the source of truth, and losing the cache costs
one slow read, never a fact.
"""

from __future__ import annotations

import gzip
import json
from typing import Any, Iterable

from hydra.events.model import Event
from hydra.kernel.snapshots import Snapshot

from .store import ControlState, TimelineRecord, WorldRecord, WorldStore

LIVE_TTL_SECONDS = 900


class RedisLiveCache:
    """Wraps a store, caching only the live-state read. Every other call passes straight through."""

    def __init__(self, store: WorldStore, url: str, *, ttl_seconds: int = LIVE_TTL_SECONDS) -> None:
        import redis  # imported here so the dependency is only needed when it is used

        self.store = store
        self.ttl_seconds = ttl_seconds
        self.client = redis.Redis.from_url(url, socket_timeout=2.0, socket_connect_timeout=2.0)
        self.hits = 0
        self.misses = 0

    # -- the cached path ----------------------------------------------------------
    @staticmethod
    def _key(timeline_id: str) -> str:
        return f"hydra:live:{timeline_id}"

    def write_live(self, snapshot: Snapshot) -> None:
        self.store.write_live(snapshot)
        try:
            payload = gzip.compress(json.dumps(snapshot.to_dict(), separators=(",", ":")).encode())
            self.client.set(self._key(snapshot.timeline_id), payload, ex=self.ttl_seconds)
        except Exception:  # noqa: BLE001 - a cache that fails must not stop a simulation
            pass

    def read_live(self, timeline_id: str) -> Snapshot | None:
        try:
            cached = self.client.get(self._key(timeline_id))
        except Exception:  # noqa: BLE001
            cached = None
        if cached:
            self.hits += 1
            return Snapshot.from_dict(json.loads(gzip.decompress(cached)))
        self.misses += 1
        snapshot = self.store.read_live(timeline_id)
        if snapshot is not None:
            self.write_live(snapshot)
        return snapshot

    # -- everything else is the store's job ---------------------------------------
    def put_world(self, record: WorldRecord) -> None:
        self.store.put_world(record)

    def get_world(self, world_id: str) -> WorldRecord | None:
        return self.store.get_world(world_id)

    def list_worlds(self) -> list[WorldRecord]:
        return self.store.list_worlds()

    def put_timeline(self, record: TimelineRecord) -> None:
        self.store.put_timeline(record)

    def get_timeline(self, timeline_id: str) -> TimelineRecord | None:
        return self.store.get_timeline(timeline_id)

    def list_timelines(self, world_id: str) -> list[TimelineRecord]:
        return self.store.list_timelines(world_id)

    def write_snapshot(self, snapshot: Snapshot) -> None:
        self.store.write_snapshot(snapshot)

    def read_snapshot(self, timeline_id: str, tick: int) -> Snapshot | None:
        return self.store.read_snapshot(timeline_id, tick)

    def nearest_snapshot(self, timeline_id: str, tick: int) -> Snapshot | None:
        return self.store.nearest_snapshot(timeline_id, tick)

    def list_snapshot_ticks(self, timeline_id: str) -> list[int]:
        return self.store.list_snapshot_ticks(timeline_id)

    def append_events(self, timeline_id: str, events: Iterable[Event]) -> int:
        return self.store.append_events(timeline_id, events)

    def read_events(self, timeline_id: str, **kwargs: Any) -> list[Event]:
        return self.store.read_events(timeline_id, **kwargs)

    def get_event(self, timeline_id: str, event_id: str) -> Event | None:
        return self.store.get_event(timeline_id, event_id)

    def count_events(self, timeline_id: str) -> int:
        return self.store.count_events(timeline_id)

    def write_telemetry(self, timeline_id: str, tick: int, metrics: dict[str, float]) -> None:
        self.store.write_telemetry(timeline_id, tick, metrics)

    def read_telemetry(self, timeline_id: str, limit: int = 200) -> list[dict[str, Any]]:
        return self.store.read_telemetry(timeline_id, limit)

    def put_control(self, control: ControlState) -> None:
        self.store.put_control(control)

    def get_control(self, world_id: str, timeline_id: str) -> ControlState | None:
        return self.store.get_control(world_id, timeline_id)
