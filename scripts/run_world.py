#!/usr/bin/env python3
"""Create and run a Hydra world from the command line.

    python scripts/run_world.py --seed 20260826 --days 3 --data ./data
    python scripts/run_world.py --scenario plant_failure --scenario-tick 720 --days 6
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for package in sorted((ROOT / "packages").iterdir()):
    if package.is_dir() and (package / "hydra").is_dir():
        sys.path.insert(0, str(package))

from hydra.kernel.clock import TICKS_PER_DAY  # noqa: E402
from hydra.kernel.config import WorldConfig  # noqa: E402
from hydra.kernel.kernelstate import KernelDomainState  # noqa: E402
from hydra.persistence.filestore import FileStore  # noqa: E402
from hydra.persistence.store import ControlState  # noqa: E402
from hydra.world import create_world  # noqa: E402
from hydra.world.scenarios import run_scenario  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Hydra World simulation")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument("--data", type=str, default="", help="persist to this directory")
    parser.add_argument("--world-id", type=str, default="world_hydra")
    parser.add_argument("--residents", type=int, default=0)
    parser.add_argument("--scenario", type=str, default="")
    parser.add_argument("--scenario-tick", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--llm",
        type=str,
        default="",
        choices=["", "gemini", "anthropic"],
        help="let the most important agents decide through a model instead of rules alone",
    )
    parser.add_argument("--llm-model", type=str, default="", help="override the model id")
    args = parser.parse_args()

    config = WorldConfig()
    if args.residents:
        config.population.total_residents = args.residents

    # Two modes, and they are not the same claim.
    #
    # Without --llm the world runs on rules and replays to the same state hash from the same
    # seed; that is what the determinism tests check. With --llm the most important agents
    # decide through a provider, and the run does not replay to the same hash, because a model
    # does not answer identically twice. The LLM section is excluded from `config_hash` so the
    # two modes are the same world, differing in how its agents think -- not two worlds.
    if args.llm:
        config.llm.enabled = True
        config.llm.provider = args.llm
        if args.llm_model:
            config.llm.small_model = args.llm_model
            config.llm.large_model = args.llm_model
    store = FileStore(args.data) if args.data else None

    started = time.perf_counter()
    runtime = create_world(config, seed=args.seed, world_id=args.world_id, store=store)
    genesis_seconds = time.perf_counter() - started
    if not args.quiet:
        print(f"genesis: {genesis_seconds:.1f}s  hash={runtime.state.state_hash()}")
        gateway = runtime.kernel.ctx.llm
        if args.llm:
            adapter = getattr(gateway, "adapter", None)
            if gateway is not None and gateway.enabled:
                print(f"llm: {config.llm.provider} · {config.llm.small_model} · {getattr(adapter, 'mode', '?')}")
            else:
                # Said out loud rather than silently degraded: a jury run that quietly fell back
                # to rules would look identical to one that worked.
                print(
                    f"llm: {config.llm.provider} UNAVAILABLE "
                    f"({getattr(adapter, 'mode', 'no adapter')}) — agents will run on rules"
                )

    total_ticks = int(args.days * TICKS_PER_DAY)
    scenario_tick = args.scenario_tick if args.scenario else -1
    started = time.perf_counter()
    for tick in range(total_ticks):
        runtime.kernel.tick()
        if runtime.state.meta.tick == scenario_tick:
            result = run_scenario(runtime, args.scenario)
            print(f"scenario {result.name} at tick {result.tick}: {result.detail}")
        if not args.quiet and runtime.state.meta.tick % TICKS_PER_DAY == 0:
            metrics = runtime.state.domain(KernelDomainState).metrics
            print(
                f"day {runtime.state.meta.tick // TICKS_PER_DAY:3d}  "
                f"unemployment={metrics.get('unemployment', 0):.3f}  "
                f"cpi={metrics.get('cpi', 0):.3f}  "
                f"energy={metrics.get('energy_price', 0):.0f}  "
                f"unrest={metrics.get('unrest_index', 0):.3f}  "
                f"approval={metrics.get('gov_approval', 0):.3f}"
            )
    runtime.flush()
    elapsed = time.perf_counter() - started
    print(
        f"ran {total_ticks} ticks in {elapsed:.1f}s "
        f"({elapsed / max(1, total_ticks) * 1000:.0f} ms/tick), final hash {runtime.state.state_hash()}"
    )

    if store is not None:
        # Publish the world as the worker would, and leave a control record for it to find.
        # Without these a persisted run is invisible: the API falls back to the genesis
        # snapshot and reports tick 0, and the worker has nothing to act on, so the city
        # looks frozen at midnight on its first day for reasons nothing explains.
        store.write_live(runtime.kernel.snapshot())
        store.put_control(
            ControlState(
                world_id=args.world_id,
                timeline_id=runtime.state.meta.timeline_id,
                mode="paused",
                speed=4.0,
                note="created by scripts/run_world.py",
            )
        )
        print(f"world {args.world_id} / {runtime.state.meta.timeline_id} ready at tick {runtime.state.meta.tick}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
