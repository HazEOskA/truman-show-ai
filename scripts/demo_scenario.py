#!/usr/bin/env python3
"""Run the required demo scenario end to end and print the chain it produces.

    python scripts/demo_scenario.py

Nothing here writes a storyline. The script starts a city, lets it settle, takes 40% off one
generator, and then just reports what the world does about it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for package in sorted((ROOT / "packages").iterdir()):
    if package.is_dir() and (package / "hydra").is_dir():
        sys.path.insert(0, str(package))

from hydra.agents.model import AgentsState  # noqa: E402
from hydra.companies.model import CompaniesState  # noqa: E402
from hydra.economy.model import EconomyState  # noqa: E402
from hydra.geography.model import GeographyState  # noqa: E402
from hydra.government.model import GovernmentState  # noqa: E402
from hydra.history.state import HistoryState  # noqa: E402
from hydra.information.model import KnowledgeState  # noqa: E402
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR  # noqa: E402
from hydra.kernel.config import WorldConfig  # noqa: E402
from hydra.kernel.kernelstate import KernelDomainState  # noqa: E402
from hydra.media.model import MediaState  # noqa: E402
from hydra.world import create_world  # noqa: E402
from hydra.world.scenarios import run_scenario  # noqa: E402


def line(runtime, label: str) -> None:
    economy = runtime.state.domain(EconomyState)
    companies = runtime.state.domain(CompaniesState)
    government = runtime.state.domain(GovernmentState)
    metrics = runtime.state.domain(KernelDomainState).metrics
    print(
        f"{label:<10} energy={economy.markets['electricity'].price_minor:>4}"
        f"  marginal={economy.markets['electricity'].cost_override_minor:>4}"
        f"  reserve={metrics.get('power_reserve_ratio', 0):.2f}"
        f"  cpi={economy.cpi:.3f}"
        f"  unemployment={economy.unemployment_rate:6.3f}"
        f"  layoffs={companies.total_layoffs:>5}"
        f"  policies={len(government.active_policies())}"
        f"  approval={government.approval:.3f}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Hydra World demo scenario")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--warmup-days", type=int, default=12)
    parser.add_argument("--after-days", type=int, default=10)
    parser.add_argument("--loss", type=float, default=0.4)
    args = parser.parse_args()

    print("1. Hydra starts from a stable state\n")
    runtime = create_world(WorldConfig(), seed=args.seed, world_id="world_demo")
    runtime.kernel.run(TICKS_PER_DAY * args.warmup_days)
    line(runtime, "stable")

    print(f"\n2. One power plant loses {args.loss:.0%} of its output")
    result = run_scenario(runtime, "plant_failure", plant_id="plant_kelvar", loss=args.loss)
    print(f"   {result.detail}\n")

    runtime.kernel.run(TICKS_PER_HOUR * 12)
    line(runtime, "+12h")
    for day in range(1, args.after_days + 1):
        runtime.kernel.run(TICKS_PER_DAY)
        line(runtime, f"day+{day}")

    media = runtime.state.domain(MediaState)
    government = runtime.state.domain(GovernmentState)
    knowledge = runtime.state.domain(KnowledgeState)
    agents = runtime.state.domain(AgentsState)
    history = runtime.state.domain(HistoryState)
    geography = runtime.state.domain(GeographyState)

    print("\n7. The media publish it — one event, several narratives")
    for publication in sorted(media.publications.values(), key=lambda p: -p.tick)[:6]:
        outlet = media.outlets[publication.outlet_id].name
        print(f"   [{outlet}] ({publication.framing}) {publication.headline}")

    print("\n8. The news reaches part of the city, not all of it")
    post_shock = [f for f in knowledge.facts.values() if f.importance >= 0.4]
    for subject in sorted(post_shock, key=lambda f: -f.importance)[:2]:
        knowing = sum(1 for pid in knowledge.knowledge if knowledge.knows(pid, subject.fact_id))
        print(f"   fact: {subject.text}")
        print(f"     known by {knowing} of {len(agents.people)} individually simulated people")
        shares = sorted(
            ((cohort, values.get(subject.fact_id, 0.0)) for cohort, values in knowledge.cohort_awareness.items()),
            key=lambda pair: -pair[1],
        )[:3]
        if shares and shares[0][1] > 0:
            for cohort_id, share in shares:
                print(f"     {cohort_id}: {share:.0%} aware")
        else:
            print("     no cohort has picked this one up yet — it travelled person to person")

    print("\n9. Behaviour changes")
    unemployed = [p for p in agents.people.values() if not p.employer_id and p.age_years >= 18 and p.alive]
    print(f"   people without work: {len(unemployed)}")
    print(f"   districts with rising unrest: "
          f"{sum(1 for d in geography.districts.values() if d.unrest > 0.06)}")

    print("\n10. The government responds")
    for policy in sorted(government.policies.values(), key=lambda p: -p.enacted_tick)[:4]:
        print(f"   t{policy.enacted_tick} {policy.kind.value} target={policy.target or '—'} value={policy.value}")
    if not government.policies:
        print("   (no policy yet — the city is still absorbing it)")

    print("\nChronicle — what the world thought was important")
    for entry in sorted(history.chronicle, key=lambda e: -e.importance)[:8]:
        print(f"   {entry.sim_time}  {entry.importance:.2f}  {entry.topic:<24} {entry.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
