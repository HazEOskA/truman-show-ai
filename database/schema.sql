-- Hydra World — PostgreSQL schema.
--
-- The store's contract is the same for both backends (see hydra.persistence.store):
-- worlds and timelines are metadata, snapshots are canonical state blobs, events are the
-- append-only ledger, telemetry is the metric stream and control is the operator's intent.
--
-- Append-only is enforced here as well as in application code: a sealed timeline cannot have
-- its past rewritten, whatever a client tries.

CREATE TABLE IF NOT EXISTS worlds (
    world_id          TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    seed              BIGINT NOT NULL,
    config_hash       TEXT NOT NULL,
    kernel_version    TEXT NOT NULL,
    config            JSONB NOT NULL DEFAULT '{}'::jsonb,
    root_timeline_id  TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS timelines (
    timeline_id         TEXT PRIMARY KEY,
    world_id            TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
    parent_timeline_id  TEXT REFERENCES timelines(timeline_id),
    fork_tick           BIGINT,
    seed                BIGINT NOT NULL,
    seed_lineage        JSONB NOT NULL DEFAULT '[]'::jsonb,
    label               TEXT NOT NULL DEFAULT '',
    sealed              BOOLEAN NOT NULL DEFAULT FALSE,
    head_tick           BIGINT NOT NULL DEFAULT 0,
    divergence_note     TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS timelines_world_idx ON timelines(world_id);

CREATE TABLE IF NOT EXISTS snapshots (
    timeline_id     TEXT NOT NULL REFERENCES timelines(timeline_id) ON DELETE CASCADE,
    tick            BIGINT NOT NULL,
    state_hash      TEXT NOT NULL,
    config_hash     TEXT NOT NULL,
    seed            BIGINT NOT NULL,
    kernel_version  TEXT NOT NULL,
    payload         BYTEA NOT NULL,          -- gzipped canonical JSON
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (timeline_id, tick)
);

CREATE TABLE IF NOT EXISTS events (
    timeline_id  TEXT NOT NULL REFERENCES timelines(timeline_id) ON DELETE CASCADE,
    event_id     TEXT NOT NULL,
    tick         BIGINT NOT NULL,
    topic        TEXT NOT NULL,
    action       TEXT NOT NULL,
    actor        TEXT,
    target       TEXT,
    location     TEXT,
    importance   REAL NOT NULL DEFAULT 0,
    visibility   TEXT NOT NULL DEFAULT 'public',
    truth        TEXT NOT NULL DEFAULT 'true',
    sim_time     TEXT NOT NULL DEFAULT '',
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    causes       JSONB NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (timeline_id, event_id)
);
CREATE INDEX IF NOT EXISTS events_tick_idx        ON events(timeline_id, tick);
CREATE INDEX IF NOT EXISTS events_topic_idx       ON events(timeline_id, topic);
CREATE INDEX IF NOT EXISTS events_actor_idx       ON events(timeline_id, actor);
CREATE INDEX IF NOT EXISTS events_importance_idx  ON events(timeline_id, importance DESC);
CREATE INDEX IF NOT EXISTS events_causes_idx      ON events USING gin (causes);

CREATE TABLE IF NOT EXISTS telemetry (
    timeline_id  TEXT NOT NULL REFERENCES timelines(timeline_id) ON DELETE CASCADE,
    tick         BIGINT NOT NULL,
    metrics      JSONB NOT NULL,
    PRIMARY KEY (timeline_id, tick)
);

CREATE TABLE IF NOT EXISTS control (
    world_id     TEXT NOT NULL,
    timeline_id  TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'paused',
    speed        REAL NOT NULL DEFAULT 1.0,
    target_tick  BIGINT,
    step_ticks   INTEGER NOT NULL DEFAULT 0,
    scenario     TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (world_id, timeline_id)
);

CREATE TABLE IF NOT EXISTS kv (
    key    TEXT PRIMARY KEY,
    value  BYTEA NOT NULL
);

-- History is not editable. A sealed timeline may only ever grow forwards.
CREATE OR REPLACE FUNCTION hydra_guard_sealed_events() RETURNS trigger AS $$
DECLARE
    is_sealed BOOLEAN;
    head      BIGINT;
BEGIN
    SELECT sealed, head_tick INTO is_sealed, head FROM timelines WHERE timeline_id = NEW.timeline_id;
    IF is_sealed AND NEW.tick < head THEN
        RAISE EXCEPTION 'timeline % is sealed at tick %; writing at tick % would rewrite history',
            NEW.timeline_id, head, NEW.tick;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS events_append_only ON events;
CREATE TRIGGER events_append_only BEFORE INSERT OR UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION hydra_guard_sealed_events();

CREATE OR REPLACE RULE events_no_delete AS ON DELETE TO events DO INSTEAD NOTHING;
