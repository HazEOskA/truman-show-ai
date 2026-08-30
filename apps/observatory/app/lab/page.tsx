"use client";

/**
 * THE LABORATORY.
 *
 * Hydra is a research instrument, and until now the Observatory presented it as fourteen
 * equally-weighted tabs. That is the right shape for someone who already knows the world and
 * the wrong shape for someone meeting it: a visitor with five minutes has no way to tell
 * which tab is the argument and which is a detail.
 *
 * So the Lab is the bench. It does three things and refuses to do a fourth:
 *
 * 1. **Shows the rig.** Which world is loaded, whether the clock is turning, and the four
 *    values that identify this world completely. If the world is paused, every mission on
 *    this page says so instead of quietly launching into a frozen city.
 * 2. **Launches experiments.** A mission is a scenario queued on the control channel plus
 *    the view worth watching while it lands — never a recording, never a second simulation.
 * 3. **States what is being tested.** Seven claims, each with the test that fails if it
 *    stops holding, so a jury can check the claim rather than take it.
 *
 * It writes operator intent and nothing else. The Observatory is read-first, and pressing
 * Run here does what pressing Run anywhere else does: leaves a note the worker picks up at a
 * tick boundary.
 */

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import WorldPicker from "@/components/WorldPicker";
import { apiPost, fmt, Json, pct, usePolling, useSelection } from "@/lib/api";
import { useCityEvents, useClock } from "@/lib/city/useCity";
import { INSTRUMENTS, MISSIONS, THESES, type LabMission } from "@/lib/lab/programme";

import "./lab.css";

export default function LabPage() {
  const router = useRouter();
  const { worldId, timelineId, select } = useSelection();
  const base = worldId ? `/worlds/${worldId}/timelines/${timelineId}` : null;
  // `/state` summarises fifty thousand residents and takes the API seconds, not
  // milliseconds. Polling it faster than it can answer only builds a queue.
  const { data: state, error } = usePolling<Json>(base ? `${base}/state` : null, 6000);
  const tick = Number(state?.tick ?? 0);
  const clock = useClock(worldId, timelineId, tick);
  const events = useCityEvents(timelineId, tick);

  const [launching, setLaunching] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const ready = Boolean(worldId && state);
  const running = clock.running;

  /**
   * Launching a mission.
   *
   * A shock is queued on the control channel and the clock is nudged into `running`, because
   * a scenario dropped into a paused world would look like nothing happening. Then the
   * visitor is handed to the view where the consequence will show up. If the queue call
   * fails, the navigation does not happen: better a visible error here than a jury staring
   * at a city where nothing is going to change.
   */
  const launch = useCallback(
    async (mission: LabMission) => {
      setNote(null);
      if (!mission.scenario) {
        router.push(mission.href);
        return;
      }
      if (!base) {
        setNote("Select a world or run Genesis first — every mission operates on the live simulation.");
        return;
      }
      setLaunching(mission.id);
      try {
        await apiPost(`${base}/scenario`, { name: mission.scenario.name, params: mission.scenario.params });
        if (!running) await apiPost(`${base}/control`, { mode: "running" });
        router.push(mission.href);
      } catch (err) {
        setNote(`The scenario could not be queued: ${(err as Error).message}`);
      } finally {
        setLaunching(null);
      }
    },
    [base, router, running]
  );

  const identity = useMemo(
    () => [
      ["SEED", state ? String(state.seed) : "—"],
      ["KERNEL", state ? String(state.kernel_version) : "—"],
      ["CONFIG HASH", state ? String(state.config_hash).slice(0, 12) : "—"],
      ["STATE HASH", state ? String(state.state_hash).slice(0, 12) : "—"],
      ["PHASE", state ? String(state.phase) : "—"],
      ["TIMELINE", state ? String(state.timeline_id) : timelineId]
    ],
    [state, timelineId]
  );

  return (
    <div className="lab">
      <header className="lab-head">
        <div>
          <div className="lab-kicker">HYDRA WORLD · OBSERVATION &amp; RESEARCH LABORATORY</div>
          <h1>Laboratory</h1>
          <p className="lab-lede">
            A mission control surface for an artificial civilization. Select a world, introduce
            a disturbance and observe how the city responds. Nothing is pre-recorded: every
            mission runs against the simulation currently resolving its next tick.
          </p>
        </div>
        <div className="lab-rig">
          <div className={`rig-lamp ${ready ? (running ? "on" : "hold") : "off"}`}>
            <span />
            {ready ? (running ? "RIG RUNNING" : "RIG ON HOLD") : "NO WORLD"}
          </div>
          <div className="rig-clock">{state ? String(state.sim_time) : "—"}</div>
          <div className="rig-tick">tick {state ? Number(state.tick).toLocaleString() : "—"}</div>
        </div>
      </header>

      {error && !state ? (
        <div className="error lab-error">
          The API is not responding ({error}). Start the runtime with <code>python scripts/dev.py</code>.
        </div>
      ) : null}

      {/* -- bench ------------------------------------------------------------------ */}

      <section className="lab-section">
        <h2>01 · Mission control</h2>
        <div className="lab-bench">
          <WorldPicker worldId={worldId} timelineId={timelineId} onSelect={select} />

          <div className="card">
            <h3>Clock</h3>
            <div className="row">
              <button
                className={running ? "primary" : ""}
                disabled={!worldId || clock.busy}
                onClick={() => (running ? clock.pause() : clock.play())}
              >
                {running ? "PAUSE" : "RUN"}
              </button>
              <button disabled={!worldId || clock.busy} onClick={() => clock.step(6)}>STEP 1 H</button>
              <button disabled={!worldId || clock.busy} onClick={() => clock.step(144)}>STEP 1 DAY</button>
              <select
                value={String(clock.control?.speed ?? 4)}
                disabled={!worldId || clock.busy}
                onChange={(event) => clock.setSpeed(Number(event.target.value))}
              >
                <option value="1">1 tick/s</option>
                <option value="4">4 ticks/s</option>
                <option value="12">12 ticks/s</option>
                <option value="48">48 ticks/s</option>
                <option value="0">max</option>
              </select>
            </div>
            <div className="lab-readout">
              <div><span>POPULATION</span><b>{state ? fmt(state.population, 0) : "—"}</b></div>
              <div><span>INDIVIDUALS</span><b>{state ? fmt(state.individuals, 0) : "—"}</b></div>
              <div><span>COMPANIES</span><b>{state ? String(state.companies) : "—"}</b></div>
              <div><span>UNEMPLOYMENT</span><b>{state ? pct(state.economy?.unemployment) : "—"}</b></div>
              <div><span>CPI</span><b>{state ? fmt(state.economy?.cpi, 3) : "—"}</b></div>
              <div><span>APPROVAL</span><b>{state ? pct(state.government?.approval) : "—"}</b></div>
            </div>
          </div>

          <div className="card">
            <h3>World identity</h3>
            <p className="lab-hint">
              These six values identify the world completely. Together they reproduce it down
              to the hash on another machine — including one with no language model configured.
            </p>
            <div className="lab-identity">
              {identity.map(([label, value]) => (
                <div key={label}><span>{label}</span><b>{value}</b></div>
              ))}
            </div>
          </div>

          <div className="card lab-live">
            <div className="lab-card-head">
              <div>
                <h3>Live event feed</h3>
                <p className="lab-hint">Immutable ledger events from the selected timeline.</p>
              </div>
              <Link href="/events" className="lab-card-link">Open ledger →</Link>
            </div>
            <div className="lab-events" aria-live="polite">
              {events.length ? events.slice(0, 6).map((event) => (
                <Link key={event.event_id} href="/events" className="lab-event">
                  <span className="lab-event-time">{event.sim_time || `tick ${event.tick}`}</span>
                  <span className="lab-event-copy">
                    <b>{event.headline || `${event.topic.replaceAll("_", " ")} · ${event.action}`}</b>
                    <small>{[event.outlet, event.district_id, event.actor].filter(Boolean).join(" · ") || event.topic}</small>
                  </span>
                  <span className="lab-event-score" title={`Importance ${event.importance.toFixed(2)}`}>
                    <i style={{ width: `${Math.max(8, Math.round(event.importance * 100))}%` }} />
                  </span>
                </Link>
              )) : (
                <div className="lab-event-empty">Waiting for ledger events from the selected timeline…</div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* -- missions --------------------------------------------------------------- */}

      <section className="lab-section">
        <h2>02 · Missions</h2>
        <p className="lab-sub">
          Six live runs for the jury. The first explains the architecture, four introduce a
          disturbance and reveal the city resolving it, and the last opens a controlled
          experiment on a forked timeline.
        </p>
        {note ? <div className="error lab-error">{note}</div> : null}
        {ready && !running ? (
          <div className="lab-warning">
            The clock is paused. Shock missions will start it automatically; Mission 01 can be
            inspected while paused, but city agents will not move.
          </div>
        ) : null}

        <div className="lab-missions">
          {MISSIONS.map((mission) => (
            <article
              key={mission.id}
              className={`mission kind-${mission.kind}`}
              style={{ "--mission": mission.colour } as React.CSSProperties}
            >
              <div className="mission-visual">
                <Image src={mission.image} alt={`${mission.name} mission environment`} fill sizes="(max-width: 700px) 100vw, (max-width: 1200px) 50vw, 33vw" />
                <div className="mission-visual-shade" />
                <header>
                  <span className="mission-code">{mission.code}</span>
                  <span className="mission-kind">
                    {mission.kind === "walkthrough" ? "WALKTHROUGH" : mission.kind === "shock" ? "DISTURBANCE" : "EXPERIMENT"}
                  </span>
                </header>
                <h3>{mission.name}</h3>
              </div>

              <div className="mission-content">
                <p className="mission-summary">{mission.summary}</p>
                <div className="mission-block">
                  <h4>WHAT IT PROVES</h4>
                  <p>{mission.proves}</p>
                </div>
                <div className="mission-block">
                  <h4>WHAT TO WATCH</h4>
                  <ul>
                    {mission.watch.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <footer>
                <button
                  className="mission-go"
                  disabled={launching === mission.id || (Boolean(mission.scenario) && !ready)}
                  onClick={() => launch(mission)}
                >
                  {launching === mission.id ? "QUEUING…" : mission.cta}
                </button>
                <span className="mission-time">{mission.duration}</span>
                {mission.scenario ? (
                  <span className="mission-scenario">scenario · {mission.scenario.name}</span>
                ) : null}
              </footer>
            </article>
          ))}
        </div>
      </section>

      {/* -- theses ----------------------------------------------------------------- */}

      <section className="lab-section">
        <h2>03 · Claims under test</h2>
        <p className="lab-sub">
          Seven claims this repository actively enforces. Each names the test that fails when
          the claim stops being true —
          <code> python -m pytest tests -q</code>.
        </p>
        <ol className="lab-theses">
          {THESES.map((thesis, index) => (
            <li key={thesis.id}>
              <span className="thesis-index">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <b>{thesis.claim}</b>
                <p>{thesis.mechanism}</p>
                <code>{thesis.test}</code>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* -- instruments ------------------------------------------------------------ */}

      <section className="lab-section">
        <h2>04 · Instruments</h2>
        <p className="lab-sub">Every Observatory view answers one specific question.</p>
        <div className="lab-instruments">
          {INSTRUMENTS.map(([href, label, question]) => (
            <Link key={href} href={href} className="instrument">
              <b>{label}</b>
              <span>{question}</span>
            </Link>
          ))}
        </div>
      </section>

      <footer className="lab-foot">
        <span>STATE(t) + AGENT_DECISIONS(t) + WORLD_RULES + DETERMINISTIC_RANDOMNESS = STATE(t+1)</span>
        <span className="lab-foot-note">
          A language model is never part of this equation. The entire simulation completes
          without a configured provider — and the determinism tests require it.
        </span>
      </footer>
    </div>
  );
}
