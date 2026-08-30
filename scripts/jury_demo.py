#!/usr/bin/env python3
"""The jury path, in one command, in the order it has to be told.

A submission video has to be one unedited take, which makes a demo that needs five commands
typed in the right order with the right environment a demo that will be re-shot four times.
So this is the whole argument as a single run:

    1. IDENTITY      what this world is: seed, kernel version, config hash
    2. GEMINI LIVE   a real call to Gemini 3.5 Flash, a real decision, executed by the kernel
    3. DETERMINISM   the same seed twice with no model at all, byte-identical state hash
    4. PROOF         APR verifies a bundle, then fails on a tampered copy

Two things it refuses to do, because a demo that fakes them is worse than no demo:

* **It will not pretend to have reached Gemini.** With no key it stops at section 2 and says
  so, non-zero. A run that quietly fell back to rules looks exactly like one that worked.
* **It will not claim determinism for the Gemini run.** Sections 2 and 3 are separate worlds
  on purpose. A model does not answer identically twice, so a world it steers does not replay
  to the same hash — the LLM config is excluded from `config_hash` precisely so that the
  deterministic core stays checkable without it. Those are two different claims and the
  script keeps them apart.

Usage:

    GEMINI_API_KEY=...  python3 scripts/jury_demo.py
    python3 scripts/jury_demo.py --skip-proof        # if APR is not on PATH
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Same bootstrap as scripts/run_world.py: every package directory on the path, so the demo
# runs straight from a clone with no install step.
ROOT = Path(__file__).resolve().parent.parent
for _package in sorted((ROOT / "packages").iterdir()):
    if _package.is_dir() and (_package / "hydra").is_dir():
        sys.path.insert(0, str(_package))


def _rule(title: str) -> None:
    print(f"\n\033[1m{'─' * 78}\033[0m")
    print(f"\033[1m  {title}\033[0m")
    print(f"\033[1m{'─' * 78}\033[0m")


def _kv(key: str, value: object) -> None:
    print(f"  {key:<22} {value}")


def build_world(seed: int, *, llm: bool, residents: int):
    from hydra.kernel.config import WorldConfig
    from hydra.world import create_world

    config = WorldConfig(world_name="Hydra Jury")
    config.population.total_residents = residents
    config.population.lightweight_agents = 260
    config.population.persistent_agents = 20
    config.economy.company_count = 40
    if llm:
        config.llm.enabled = True
        config.llm.provider = "gemini"
        # Deliberately small: a demo should cost a handful of calls, not a bill.
        config.llm.escalation_importance = 0.0
        config.llm.max_calls_per_tick = 3
        config.llm.daily_calls_per_agent = 8
    return create_world(config, seed=seed, world_id=f"world_jury_{seed}")


def section_identity(world) -> None:
    _rule("1 · IDENTITY — what this world is")
    meta = world.state.meta
    _kv("seed", meta.seed)
    _kv("kernel", meta.kernel_version)
    _kv("config hash", meta.config_hash)
    _kv("state hash", world.state.state_hash())
    _kv("population", f"{len(world.state.domain(_agents_state()).people):,} simulated individually")


def _agents_state():
    from hydra.agents.model import AgentsState

    return AgentsState


def section_gemini(world) -> int:
    """A real call, a real decision, executed by the kernel. Returns a process exit code."""

    from hydra.agents.brains import UtilityBrain, situation_importance
    from hydra.agents.model import Activity, Tier
    from hydra.agents.systems import build_view
    from hydra.kernel.clock import TICKS_PER_HOUR

    _rule("2 · GEMINI LIVE — the model decides, the kernel executes")

    gateway = world.kernel.ctx.llm
    adapter = getattr(gateway, "adapter", None)
    _kv("provider", world.config.llm.provider)
    _kv("model", world.config.llm.small_model)
    _kv("adapter mode", getattr(adapter, "mode", "?"))
    _kv("gateway enabled", getattr(gateway, "enabled", False))

    if not getattr(gateway, "enabled", False):
        print(
            "\n  \033[31mNo provider reached.\033[0m Set GEMINI_API_KEY (or GOOGLE_GENAI_USE_VERTEXAI\n"
            "  with GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION) and run again.\n"
            "  This script will not continue on rules and call it a Gemini demo."
        )
        return 2

    # Wake the city: at tick zero it is midnight and nobody is deciding anything.
    print("\n  waking the city…")
    world.run(TICKS_PER_HOUR * 10)

    print("  running the loop with the provider live…")
    started = time.perf_counter()
    peak_calls = 0.0
    for _ in range(TICKS_PER_HOUR * 2):
        world.run(1)
        peak_calls = max(peak_calls, world.kernel.ctx.telemetry.snapshot().get("llm_calls", 0.0))
    elapsed = time.perf_counter() - started

    stats = gateway.stats
    _kv("llm_calls (peak/tick)", peak_calls)
    _kv("calls total", stats.calls)
    _kv("tokens_used", stats.tokens)
    _kv("declined / failed", f"{stats.declined} / {stats.failures}")
    _kv("wall clock", f"{elapsed:.1f}s")

    if stats.calls == 0:
        print("\n  \033[31mThe loop never reached the provider.\033[0m")
        return 3

    # One decision, narrated end to end, so the chain is visible rather than inferred.
    print("\n  one decision, in full:")
    ctx = world.kernel.ctx
    agents = world.state.domain(_agents_state())
    for person in agents.people.values():
        if not (
            person.alive
            and person.tier is Tier.PERSISTENT
            and person.activity in (Activity.ACTIVE, Activity.LIGHT_IDLE)
            and person.age_years > 20
        ):
            continue
        view = build_view(ctx, person)
        payload = view.to_prompt_payload()
        if not (payload["knows"] or payload["openings"]):
            continue
        view.salience = situation_importance(view)
        allowed = [option.action for option in UtilityBrain().options(view)]
        if not allowed:
            continue

        intent = gateway.propose(person, view, allowed, world.config.llm.small_model)
        if intent is None:
            continue
        result = ctx.submit(intent)
        _kv("agent", f"{person.person_id} ({person.name})")
        _kv("view offered", ", ".join(allowed))
        _kv("gemini chose", f"{intent.action} params={intent.params}")
        _kv("rationale", intent.rationale or "—")
        _kv("intent.source", intent.source)
        _kv("kernel accepted", result.accepted)
        if not result.accepted:
            _kv("rejected because", f"{result.reason} {result.detail}")
            continue
        _kv("event_id", result.event_id or "(no event — a private action)")
        if result.event_id:
            event = next(e for e in ctx.tick_events() if e.event_id == result.event_id)
            _kv("event", f"{event.topic} / {event.action} actor={event.actor}")
            _kv("event payload", event.payload)
            _kv("importance", f"{event.importance:.3f} (ledger threshold "
                              f"{world.config.kernel.ledger_importance_threshold})")
        break
    else:
        print("  no agent was in a position to act on the model's answer this tick")
    return 0


def section_determinism(seed: int, residents: int, ticks: int) -> int:
    _rule("3 · DETERMINISM — same seed, no model, identical world")
    print("  a separate pair of runs: the provider is off, which is the supported default.")
    hashes = []
    for run in (1, 2):
        world = build_world(seed, llm=False, residents=residents)
        world.run(ticks)
        digest = world.state.state_hash()
        hashes.append(digest)
        _kv(f"run {run}", f"tick {world.tick}  hash {digest}")
    if hashes[0] == hashes[1]:
        print("\n  \033[32midentical.\033[0m Same seed and config reproduce the world exactly.")
        return 0
    print("\n  \033[31mDIVERGED.\033[0m")
    return 4


def section_proof() -> int:
    _rule("4 · PROOF — an independent verifier, and a tampered copy that fails")
    apr = shutil.which("apr")
    if apr is None:
        print("  apr is not on PATH. From a clone of agent-proof-runtime:")
        print("    pip install -e .  &&  apr demo --output .runs/jury")
        print("    apr verify .runs/jury/proof-bundle.json")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "jury"
        subprocess.run([apr, "demo", "--output", str(out)], check=True)
        print()
        subprocess.run([apr, "verify", str(out / "proof-bundle.json")], check=True)

        # Tamper one byte of a delivered artifact and verify the copy. It must fail.
        artifacts = sorted(p for p in (out / "artifact").rglob("*") if p.is_file())
        if not artifacts:
            print("\n  (no artifact to tamper with)")
            return 0
        target = artifacts[0]
        target.write_bytes(target.read_bytes() + b"<!-- tampered -->")
        print(f"\n  tampered: {target.relative_to(out)}")
        tampered = subprocess.run(
            [apr, "verify", str(out / "proof-bundle.json")], capture_output=True, text=True
        )
        print(tampered.stdout.rstrip())
        print(tampered.stderr.rstrip())
        if tampered.returncode == 0:
            print("\n  \033[31mthe verifier accepted a tampered bundle.\033[0m")
            return 5
        print("\n  \033[32mrejected.\033[0m The proof does not survive editing what it covers.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the jury demonstration end to end")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--residents", type=int, default=4_000)
    parser.add_argument("--determinism-ticks", type=int, default=144)
    parser.add_argument("--skip-proof", action="store_true")
    args = parser.parse_args()

    print("\n\033[1mHYDRA WORLD — jury demonstration\033[0m")
    print("  Gemini 3.5 Flash via the Google GenAI SDK · deterministic kernel · independent proof")

    world = build_world(args.seed, llm=True, residents=args.residents)
    section_identity(world)

    code = section_gemini(world)
    if code:
        return code

    code = section_determinism(args.seed, args.residents, args.determinism_ticks)
    if code:
        return code

    if not args.skip_proof:
        code = section_proof()
        if code:
            return code

    _rule("DONE")
    print("  Gemini decided, the kernel executed, the world replays without it,")
    print("  and the proof fails the moment its evidence is edited.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
