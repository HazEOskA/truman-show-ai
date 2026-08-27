"""PostgreSQL store.

Same contract as the file store, same append-only guarantee — enforced twice, once here and
once by the trigger in ``database/schema.sql``. Used by ``docker compose``; the file store
remains the default so nothing about the simulation depends on a running database.
"""

from __future__ import annotations

import gzip
import json
from typing import Any, Iterable

from hydra.events.model import Event
from hydra.kernel.errors import SealedTimelineError
from hydra.kernel.serialization import decode, encode
from hydra.kernel.snapshots import Snapshot

from .store import ControlState, TimelineRecord, WorldRecord

try:  # psycopg is only needed when this backend is actually used
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Json
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "PostgresStore requires psycopg: pip install 'psycopg[binary]'"
    ) from exc


class PostgresStore:
    def __init__(self, dsn: str, *, schema_path: str | None = None) -> None:
        self.dsn = dsn
        self._pool: psycopg.Connection | None = None
        if schema_path:
            self.apply_schema(schema_path)

    # -- plumbing -----------------------------------------------------------------
    def _connect(self) -> psycopg.Connection:
        """The connection, reconnecting when the last one died under us.

        ``closed`` only becomes true after *we* close it. A managed Postgres that drops an
        idle connection -- which Cloud SQL does routinely -- leaves it open as far as this
        process is concerned and merely unusable, so checking ``closed`` alone means the
        store stays broken until the container restarts. ``broken`` is psycopg's own verdict
        on a connection it has found unusable, and reconnecting on it is what turns a fatal
        outage into one failed request.
        """

        connection = self._pool
        if connection is None or connection.closed or getattr(connection, "broken", False):
            self._pool = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)
        return self._pool

    def apply_schema(self, schema_path: str) -> None:
        with open(schema_path, "r", encoding="utf-8") as handle:
            sql = handle.read()
        with self._connect().cursor() as cur:
            cur.execute(sql)

    def close(self) -> None:
        if self._pool is not None and not self._pool.closed:
            self._pool.close()

    # -- worlds -------------------------------------------------------------------
    def put_world(self, record: WorldRecord) -> None:
        with self._connect().cursor() as cur:
            cur.execute(
                """
                INSERT INTO worlds (world_id, name, seed, config_hash, kernel_version, config, root_timeline_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (world_id) DO UPDATE SET
                    name = EXCLUDED.name, config = EXCLUDED.config,
                    root_timeline_id = EXCLUDED.root_timeline_id
                """,
                (
                    record.world_id,
                    record.name,
                    record.seed,
                    record.config_hash,
                    record.kernel_version,
                    Json(record.config),
                    record.root_timeline_id,
                ),
            )

    def get_world(self, world_id: str) -> WorldRecord | None:
        with self._connect().cursor() as cur:
            cur.execute("SELECT * FROM worlds WHERE world_id = %s", (world_id,))
            row = cur.fetchone()
        return _world(row) if row else None

    def list_worlds(self) -> list[WorldRecord]:
        with self._connect().cursor() as cur:
            cur.execute("SELECT * FROM worlds ORDER BY created_at")
            return [_world(row) for row in cur.fetchall()]

    # -- timelines ----------------------------------------------------------------
    def put_timeline(self, record: TimelineRecord) -> None:
        with self._connect().cursor() as cur:
            cur.execute(
                """
                INSERT INTO timelines (timeline_id, world_id, parent_timeline_id, fork_tick, seed,
                                       seed_lineage, label, sealed, head_tick, divergence_note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (timeline_id) DO UPDATE SET
                    label = EXCLUDED.label, sealed = EXCLUDED.sealed,
                    head_tick = GREATEST(timelines.head_tick, EXCLUDED.head_tick),
                    divergence_note = EXCLUDED.divergence_note
                """,
                (
                    record.timeline_id,
                    record.world_id,
                    record.parent_timeline_id,
                    record.fork_tick,
                    record.seed,
                    Json(record.seed_lineage),
                    record.label,
                    record.sealed,
                    record.head_tick,
                    record.divergence_note,
                ),
            )

    def get_timeline(self, timeline_id: str) -> TimelineRecord | None:
        with self._connect().cursor() as cur:
            cur.execute("SELECT * FROM timelines WHERE timeline_id = %s", (timeline_id,))
            row = cur.fetchone()
        return _timeline(row) if row else None

    def list_timelines(self, world_id: str) -> list[TimelineRecord]:
        with self._connect().cursor() as cur:
            cur.execute("SELECT * FROM timelines WHERE world_id = %s ORDER BY created_at", (world_id,))
            return [_timeline(row) for row in cur.fetchall()]

    def _bump_head(self, timeline_id: str, tick: int) -> None:
        with self._connect().cursor() as cur:
            cur.execute(
                "UPDATE timelines SET head_tick = GREATEST(head_tick, %s) WHERE timeline_id = %s",
                (tick, timeline_id),
            )

    def _guard_append_only(self, timeline_id: str, tick: int) -> None:
        record = self.get_timeline(timeline_id)
        if record and record.sealed and tick < record.head_tick:
            raise SealedTimelineError(
                f"timeline {timeline_id} is sealed at tick {record.head_tick}; "
                f"writing at tick {tick} would rewrite history. Fork instead."
            )

    # -- snapshots ----------------------------------------------------------------
    def write_snapshot(self, snapshot: Snapshot) -> None:
        payload = gzip.compress(json.dumps(snapshot.payload, separators=(",", ":")).encode())
        with self._connect().cursor() as cur:
            cur.execute(
                """
                INSERT INTO snapshots (timeline_id, tick, state_hash, config_hash, seed, kernel_version, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (timeline_id, tick) DO UPDATE SET
                    state_hash = EXCLUDED.state_hash, payload = EXCLUDED.payload
                """,
                (
                    snapshot.timeline_id,
                    snapshot.tick,
                    snapshot.state_hash,
                    snapshot.config_hash,
                    snapshot.seed,
                    snapshot.kernel_version,
                    payload,
                ),
            )
        self._bump_head(snapshot.timeline_id, snapshot.tick)

    def read_snapshot(self, timeline_id: str, tick: int) -> Snapshot | None:
        with self._connect().cursor() as cur:
            cur.execute("SELECT * FROM snapshots WHERE timeline_id = %s AND tick = %s", (timeline_id, tick))
            row = cur.fetchone()
        return _snapshot(row) if row else None

    def nearest_snapshot(self, timeline_id: str, tick: int) -> Snapshot | None:
        with self._connect().cursor() as cur:
            cur.execute(
                "SELECT * FROM snapshots WHERE timeline_id = %s AND tick <= %s ORDER BY tick DESC LIMIT 1",
                (timeline_id, tick),
            )
            row = cur.fetchone()
        return _snapshot(row) if row else None

    def list_snapshot_ticks(self, timeline_id: str) -> list[int]:
        with self._connect().cursor() as cur:
            cur.execute("SELECT tick FROM snapshots WHERE timeline_id = %s ORDER BY tick", (timeline_id,))
            return [int(row["tick"]) for row in cur.fetchall()]

    def write_live(self, snapshot: Snapshot) -> None:
        payload = gzip.compress(json.dumps(snapshot.to_dict(), separators=(",", ":")).encode())
        with self._connect().cursor() as cur:
            cur.execute(
                """
                INSERT INTO kv (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (f"live:{snapshot.timeline_id}", payload),
            )
        self._bump_head(snapshot.timeline_id, snapshot.tick)

    def read_live(self, timeline_id: str) -> Snapshot | None:
        with self._connect().cursor() as cur:
            cur.execute("SELECT value FROM kv WHERE key = %s", (f"live:{timeline_id}",))
            row = cur.fetchone()
        if not row:
            return None
        return Snapshot.from_dict(json.loads(gzip.decompress(bytes(row["value"]))))

    # -- events -------------------------------------------------------------------
    def append_events(self, timeline_id: str, events: Iterable[Event]) -> int:
        batch = list(events)
        if not batch:
            return 0
        self._guard_append_only(timeline_id, min(e.tick for e in batch))
        rows = [
            (
                timeline_id,
                e.event_id,
                e.tick,
                e.topic,
                e.action,
                e.actor,
                e.target,
                e.location,
                e.importance,
                e.visibility.value,
                e.truth.value,
                e.sim_time,
                Json(encode(e.payload)),
                Json(e.causes),
            )
            for e in batch
        ]
        with self._connect().cursor() as cur:
            cur.executemany(
                """
                INSERT INTO events (timeline_id, event_id, tick, topic, action, actor, target, location,
                                    importance, visibility, truth, sim_time, payload, causes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (timeline_id, event_id) DO NOTHING
                """,
                rows,
            )
        self._bump_head(timeline_id, max(e.tick for e in batch))
        return len(batch)

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
        clauses = ["timeline_id = %s", "tick >= %s", "importance >= %s"]
        params: list[Any] = [timeline_id, start_tick, min_importance]
        if end_tick is not None:
            clauses.append("tick <= %s")
            params.append(end_tick)
        if actor:
            clauses.append("(actor = %s OR target = %s)")
            params.extend([actor, actor])
        if topics:
            ors = []
            for topic in topics:
                if topic.endswith("*"):
                    ors.append("topic LIKE %s")
                    params.append(topic[:-1] + "%")
                else:
                    ors.append("topic = %s")
                    params.append(topic)
            clauses.append("(" + " OR ".join(ors) + ")")
        order = "DESC" if newest_first else "ASC"
        params.append(limit)
        with self._connect().cursor() as cur:
            cur.execute(
                f"SELECT * FROM events WHERE {' AND '.join(clauses)} "
                f"ORDER BY tick {order}, event_id {order} LIMIT %s",
                params,
            )
            return [_event(row) for row in cur.fetchall()]

    def get_event(self, timeline_id: str, event_id: str) -> Event | None:
        with self._connect().cursor() as cur:
            cur.execute(
                "SELECT * FROM events WHERE timeline_id = %s AND event_id = %s", (timeline_id, event_id)
            )
            row = cur.fetchone()
        return _event(row) if row else None

    def count_events(self, timeline_id: str) -> int:
        with self._connect().cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM events WHERE timeline_id = %s", (timeline_id,))
            return int(cur.fetchone()["n"])

    # -- telemetry / control ------------------------------------------------------
    def write_telemetry(self, timeline_id: str, tick: int, metrics: dict[str, float]) -> None:
        with self._connect().cursor() as cur:
            cur.execute(
                """
                INSERT INTO telemetry (timeline_id, tick, metrics) VALUES (%s, %s, %s)
                ON CONFLICT (timeline_id, tick) DO UPDATE SET metrics = EXCLUDED.metrics
                """,
                (timeline_id, tick, Json(metrics)),
            )

    def read_telemetry(self, timeline_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect().cursor() as cur:
            cur.execute(
                "SELECT tick, metrics FROM telemetry WHERE timeline_id = %s ORDER BY tick DESC LIMIT %s",
                (timeline_id, limit),
            )
            rows = [{"tick": int(r["tick"]), "metrics": r["metrics"]} for r in cur.fetchall()]
        return list(reversed(rows))

    def put_control(self, control: ControlState) -> None:
        with self._connect().cursor() as cur:
            cur.execute(
                """
                INSERT INTO control (world_id, timeline_id, mode, speed, target_tick, step_ticks, scenario, note, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (world_id, timeline_id) DO UPDATE SET
                    mode = EXCLUDED.mode, speed = EXCLUDED.speed, target_tick = EXCLUDED.target_tick,
                    step_ticks = EXCLUDED.step_ticks, scenario = EXCLUDED.scenario,
                    note = EXCLUDED.note, updated_at = now()
                """,
                (
                    control.world_id,
                    control.timeline_id,
                    control.mode,
                    control.speed,
                    control.target_tick,
                    control.step_ticks,
                    control.scenario,
                    control.note,
                ),
            )

    def get_control(self, world_id: str, timeline_id: str) -> ControlState | None:
        with self._connect().cursor() as cur:
            cur.execute(
                "SELECT * FROM control WHERE world_id = %s AND timeline_id = %s", (world_id, timeline_id)
            )
            row = cur.fetchone()
        if not row:
            return None
        return ControlState(
            world_id=row["world_id"],
            timeline_id=row["timeline_id"],
            mode=row["mode"],
            speed=float(row["speed"]),
            target_tick=row["target_tick"],
            step_ticks=int(row["step_ticks"]),
            scenario=row["scenario"],
            note=row["note"],
            updated_at=str(row["updated_at"]),
        )


def _world(row: dict[str, Any]) -> WorldRecord:
    return WorldRecord(
        world_id=row["world_id"],
        name=row["name"],
        seed=int(row["seed"]),
        config_hash=row["config_hash"],
        kernel_version=row["kernel_version"],
        config=row["config"] or {},
        created_at=str(row["created_at"]),
        root_timeline_id=row["root_timeline_id"],
    )


def _timeline(row: dict[str, Any]) -> TimelineRecord:
    return TimelineRecord(
        timeline_id=row["timeline_id"],
        world_id=row["world_id"],
        parent_timeline_id=row["parent_timeline_id"],
        fork_tick=row["fork_tick"],
        seed=int(row["seed"]),
        seed_lineage=list(row["seed_lineage"] or []),
        label=row["label"],
        sealed=bool(row["sealed"]),
        head_tick=int(row["head_tick"]),
        created_at=str(row["created_at"]),
        divergence_note=row["divergence_note"],
    )


def _snapshot(row: dict[str, Any]) -> Snapshot:
    return Snapshot(
        world_id="",
        timeline_id=row["timeline_id"],
        tick=int(row["tick"]),
        state_hash=row["state_hash"],
        config_hash=row["config_hash"],
        seed=int(row["seed"]),
        kernel_version=row["kernel_version"],
        payload=json.loads(gzip.decompress(bytes(row["payload"]))),
    )


def _event(row: dict[str, Any]) -> Event:
    return decode(
        Event,
        {
            "event_id": row["event_id"],
            "tick": int(row["tick"]),
            "topic": row["topic"],
            "action": row["action"],
            "actor": row["actor"],
            "target": row["target"],
            "location": row["location"],
            "payload": row["payload"] or {},
            "causes": list(row["causes"] or []),
            "importance": float(row["importance"]),
            "visibility": row["visibility"],
            "truth": row["truth"],
            "sim_time": row["sim_time"],
            "timeline_id": row["timeline_id"],
        },
    )
