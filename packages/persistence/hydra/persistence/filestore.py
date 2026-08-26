"""Filesystem store — the default backend.

Chosen so ``pytest`` and ``python scripts/run_world.py`` work with zero services running.
Snapshots are gzipped canonical JSON; the ledger is a gzip-member-per-flush JSONL stream,
which appends cheaply and still reads back with a plain ``gzip.open``.
"""

from __future__ import annotations

import gzip
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from hydra.events.model import Event
from hydra.kernel.errors import SealedTimelineError
from hydra.kernel.serialization import decode, encode
from hydra.kernel.snapshots import Snapshot

from .store import ControlState, TimelineRecord, WorldRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class FileStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths --------------------------------------------------------------------
    def _world_dir(self, world_id: str) -> Path:
        return self.root / "worlds" / world_id

    def _timeline_dir(self, timeline_id: str) -> Path:
        return self.root / "timelines" / timeline_id

    # -- worlds -------------------------------------------------------------------
    def put_world(self, record: WorldRecord) -> None:
        path = self._world_dir(record.world_id)
        path.mkdir(parents=True, exist_ok=True)
        if not record.created_at:
            record.created_at = _now()
        _write_json(path / "world.json", asdict(record))

    def get_world(self, world_id: str) -> WorldRecord | None:
        raw = _read_json(self._world_dir(world_id) / "world.json")
        return WorldRecord(**raw) if raw else None

    def list_worlds(self) -> list[WorldRecord]:
        base = self.root / "worlds"
        if not base.exists():
            return []
        worlds = [self.get_world(p.name) for p in sorted(base.iterdir()) if p.is_dir()]
        return [w for w in worlds if w is not None]

    # -- timelines ----------------------------------------------------------------
    def put_timeline(self, record: TimelineRecord) -> None:
        path = self._timeline_dir(record.timeline_id)
        path.mkdir(parents=True, exist_ok=True)
        if not record.created_at:
            record.created_at = _now()
        _write_json(path / "timeline.json", asdict(record))

    def get_timeline(self, timeline_id: str) -> TimelineRecord | None:
        raw = _read_json(self._timeline_dir(timeline_id) / "timeline.json")
        return TimelineRecord(**raw) if raw else None

    def list_timelines(self, world_id: str) -> list[TimelineRecord]:
        base = self.root / "timelines"
        if not base.exists():
            return []
        out = []
        for path in sorted(base.iterdir()):
            record = self.get_timeline(path.name)
            if record and record.world_id == world_id:
                out.append(record)
        return out

    def _bump_head(self, timeline_id: str, tick: int) -> None:
        record = self.get_timeline(timeline_id)
        if record is None:
            return
        if tick > record.head_tick:
            record.head_tick = tick
            self.put_timeline(record)

    def _guard_append_only(self, timeline_id: str, tick: int) -> None:
        record = self.get_timeline(timeline_id)
        if record is None or not record.sealed:
            return
        if tick < record.head_tick:
            raise SealedTimelineError(
                f"timeline {timeline_id} is sealed at tick {record.head_tick}; "
                f"writing at tick {tick} would rewrite history. Fork instead."
            )

    # -- snapshots ----------------------------------------------------------------
    def write_snapshot(self, snapshot: Snapshot) -> None:
        path = self._timeline_dir(snapshot.timeline_id) / "snapshots"
        path.mkdir(parents=True, exist_ok=True)
        target = path / f"{snapshot.name}.json.gz"
        if target.exists():
            existing = Snapshot.from_dict(json.loads(gzip.decompress(target.read_bytes())))
            if existing.state_hash != snapshot.state_hash:
                self._guard_append_only(snapshot.timeline_id, snapshot.tick)
        target.write_bytes(gzip.compress(json.dumps(snapshot.to_dict(), separators=(",", ":")).encode()))
        self._bump_head(snapshot.timeline_id, snapshot.tick)

    def write_live(self, snapshot: Snapshot) -> None:
        """The current world, overwritten as it runs. Snapshots are history; this is 'now'."""

        path = self._timeline_dir(snapshot.timeline_id)
        path.mkdir(parents=True, exist_ok=True)
        target = path / "live.json.gz"
        tmp = path / "live.json.gz.tmp"
        tmp.write_bytes(gzip.compress(json.dumps(snapshot.to_dict(), separators=(",", ":")).encode()))
        os.replace(tmp, target)
        self._bump_head(snapshot.timeline_id, snapshot.tick)

    def read_live(self, timeline_id: str) -> Snapshot | None:
        target = self._timeline_dir(timeline_id) / "live.json.gz"
        if not target.exists():
            return None
        return Snapshot.from_dict(json.loads(gzip.decompress(target.read_bytes())))

    def read_snapshot(self, timeline_id: str, tick: int) -> Snapshot | None:
        target = self._timeline_dir(timeline_id) / "snapshots" / f"snapshot_{tick:09d}.json.gz"
        if not target.exists():
            return None
        return Snapshot.from_dict(json.loads(gzip.decompress(target.read_bytes())))

    def list_snapshot_ticks(self, timeline_id: str) -> list[int]:
        path = self._timeline_dir(timeline_id) / "snapshots"
        if not path.exists():
            return []
        return sorted(int(p.name[len("snapshot_") : -len(".json.gz")]) for p in path.glob("snapshot_*.json.gz"))

    def nearest_snapshot(self, timeline_id: str, tick: int) -> Snapshot | None:
        ticks = [t for t in self.list_snapshot_ticks(timeline_id) if t <= tick]
        if not ticks:
            return None
        return self.read_snapshot(timeline_id, ticks[-1])

    # -- events -------------------------------------------------------------------
    def _events_path(self, timeline_id: str) -> Path:
        path = self._timeline_dir(timeline_id)
        path.mkdir(parents=True, exist_ok=True)
        return path / "events.jsonl.gz"

    def append_events(self, timeline_id: str, events: Iterable[Event]) -> int:
        batch = list(events)
        if not batch:
            return 0
        self._guard_append_only(timeline_id, min(e.tick for e in batch))
        blob = "\n".join(json.dumps(encode(e), separators=(",", ":")) for e in batch) + "\n"
        with open(self._events_path(timeline_id), "ab") as fh:
            fh.write(gzip.compress(blob.encode("utf-8")))
        self._bump_head(timeline_id, max(e.tick for e in batch))
        return len(batch)

    def _iter_events(self, timeline_id: str):
        path = self._events_path(timeline_id)
        if not path.exists() or path.stat().st_size == 0:
            return
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield decode(Event, json.loads(line))

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
    ) -> list[Event]:
        found: list[Event] = []
        for event in self._iter_events(timeline_id):
            if event.tick < start_tick:
                continue
            if end_tick is not None and event.tick > end_tick:
                continue
            if event.importance < min_importance:
                continue
            if actor and event.actor != actor and event.target != actor:
                continue
            if topics and not any(_topic_match(t, event.topic) for t in topics):
                continue
            found.append(event)
        found.sort(key=lambda e: (e.tick, e.event_id), reverse=newest_first)
        return found[:limit]

    def get_event(self, timeline_id: str, event_id: str) -> Event | None:
        for event in self._iter_events(timeline_id):
            if event.event_id == event_id:
                return event
        return None

    def count_events(self, timeline_id: str) -> int:
        return sum(1 for _ in self._iter_events(timeline_id))

    # -- telemetry / control ------------------------------------------------------
    def write_telemetry(self, timeline_id: str, tick: int, metrics: dict[str, float]) -> None:
        path = self._timeline_dir(timeline_id)
        path.mkdir(parents=True, exist_ok=True)
        row = {"tick": tick, "metrics": metrics}
        with open(path / "telemetry.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    def read_telemetry(self, timeline_id: str, limit: int = 200) -> list[dict[str, Any]]:
        path = self._timeline_dir(timeline_id) / "telemetry.jsonl"
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        return rows[-limit:]

    def put_control(self, control: ControlState) -> None:
        path = self._world_dir(control.world_id)
        path.mkdir(parents=True, exist_ok=True)
        control.updated_at = _now()
        _write_json(path / f"control_{control.timeline_id}.json", asdict(control))

    def get_control(self, world_id: str, timeline_id: str) -> ControlState | None:
        raw = _read_json(self._world_dir(world_id) / f"control_{timeline_id}.json")
        return ControlState(**raw) if raw else None


def _topic_match(pattern: str, topic: str) -> bool:
    if pattern.endswith("*"):
        return topic.startswith(pattern[:-1])
    return pattern == topic


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
