"""Performance and scaling smoke tests (spec sections 26 and 38).

These are not benchmarks with a fixed budget — CI machines vary too much for that. They check
the properties the architecture claims: the cost of a tick is bounded by the compute governor
rather than by the population, sleeping agents are genuinely free, and the world scales
sub-linearly because most people are cohorts.
"""

from __future__ import annotations

import time

import pytest

from hydra.agents.model import AgentsState
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR
from hydra.kernel.kernelstate import KernelDomainState
from hydra.world import create_world

from conftest import small_config


def _timed_run(config, seed: int, ticks: int) -> tuple[float, object]:
    runtime = create_world(config, seed=seed, world_id=f"world_perf_{seed}")
    started = time.perf_counter()
    runtime.kernel.run(ticks)
    return time.perf_counter() - started, runtime


def test_a_simulated_day_completes_in_reasonable_time():
    elapsed, runtime = _timed_run(small_config(), 4001, TICKS_PER_DAY)
    per_tick_ms = elapsed / TICKS_PER_DAY * 1000
    assert runtime.state.meta.tick == TICKS_PER_DAY
    assert per_tick_ms < 250, f"{per_tick_ms:.1f} ms/tick is too slow for a small city"


def test_brain_evaluations_are_capped_by_the_compute_governor():
    config = small_config()
    config.agents.max_brain_evaluations_per_tick = 50
    runtime = create_world(config, seed=4002, world_id="world_budget")
    runtime.kernel.run(TICKS_PER_HOUR * 12)

    metrics = runtime.state.domain(KernelDomainState).metrics
    assert metrics.get("agent_ticks", 0) <= 50, "the priority queue must respect its budget"


def test_population_grows_faster_than_the_cost_of_simulating_it():
    """Cohorts are the point: four times the people must not cost four times the time."""

    small = small_config()
    big = small_config()
    big.population.total_residents = small.population.total_residents * 4
    # The individually simulated headcount stays the same; the extra people are cohorts.
    big.population.lightweight_agents = small.population.lightweight_agents

    small_elapsed, small_runtime = _timed_run(small, 4003, TICKS_PER_HOUR * 6)
    big_elapsed, big_runtime = _timed_run(big, 4003, TICKS_PER_HOUR * 6)

    assert big_runtime.state.domain(AgentsState).total_population() > (
        small_runtime.state.domain(AgentsState).total_population() * 2
    )
    assert big_elapsed < small_elapsed * 2.5, (
        f"four times the population cost {big_elapsed / max(small_elapsed, 1e-6):.1f}x the time"
    )


def test_sleeping_is_free():
    runtime = create_world(small_config(), seed=4004, world_id="world_free")
    from hydra.kernel.clock import SimClock

    runtime.kernel.run(SimClock.tick_at_hour(0, 14.0))
    day_started = time.perf_counter()
    runtime.kernel.run(TICKS_PER_HOUR * 4)
    day_cost = time.perf_counter() - day_started

    runtime.kernel.run(TICKS_PER_DAY + SimClock.tick_at_hour(0, 1.0) - runtime.state.meta.tick)
    night_started = time.perf_counter()
    runtime.kernel.run(TICKS_PER_HOUR * 4)
    night_cost = time.perf_counter() - night_started

    assert night_cost < day_cost, f"night ({night_cost:.2f}s) should be cheaper than day ({day_cost:.2f}s)"


@pytest.mark.parametrize("ticks", [12, 60])
def test_tick_cost_does_not_grow_without_bound(ticks: int):
    """A world that gets slower every tick is a world with a leak in it."""

    runtime = create_world(small_config(), seed=4005, world_id="world_drift")
    runtime.kernel.run(TICKS_PER_HOUR)

    first_started = time.perf_counter()
    runtime.kernel.run(ticks)
    first = time.perf_counter() - first_started

    runtime.kernel.run(TICKS_PER_DAY)

    later_started = time.perf_counter()
    runtime.kernel.run(ticks)
    later = time.perf_counter() - later_started

    assert later < first * 4 + 0.5, f"tick cost grew from {first:.2f}s to {later:.2f}s"
