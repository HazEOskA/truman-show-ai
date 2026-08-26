"""Spec section 33 — the sleep test.

An agent that falls asleep at 23:00 must cost the world nothing until it wakes: no brain
evaluation, no LLM call, no per-tick decision. The night is one skip. What happened while it
slept reaches the agent afterwards, as a delta summary built from its own inbox.
"""

from __future__ import annotations

from hydra.agents.model import Activity, AgentsState, Tier
from hydra.agents.systems import AgentBrainSystem
from hydra.dormancy.engine import schedule_for, should_sleep, wake_tick_for
from hydra.dormancy.systems import DormancySystem
from hydra.information.model import KnowledgeState, Observation, Source
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR, SimClock
from hydra.memory.model import MemoryState
from hydra.world import create_world

from conftest import small_config


def test_agents_sleep_at_night_and_wake_in_the_morning():
    """Chronotypes differ, so the city does not switch off at once — but it does switch off."""

    runtime = create_world(small_config(), seed=808, world_id="world_sleep")
    agents = runtime.state.domain(AgentsState)

    # 03:00 the following night: the deep-sleep hour for every chronotype.
    runtime.kernel.run(TICKS_PER_DAY + SimClock.tick_at_hour(0, 3.0))
    night = sum(1 for p in agents.people.values() if p.activity is Activity.SLEEP)
    assert night > len(agents.people) * 0.8, "the city should be asleep at 03:00"

    # …and awake again by mid-morning.
    runtime.kernel.run(SimClock.tick_at_hour(0, 11.0) + TICKS_PER_DAY - (runtime.state.meta.tick % TICKS_PER_DAY) - TICKS_PER_DAY)
    morning = sum(1 for p in agents.people.values() if p.activity is Activity.SLEEP)
    assert morning < night * 0.35, "the city should be awake by mid-morning"


def test_a_named_agent_sleeps_through_its_own_night():
    """Spec section 33 read literally: one agent, its own 23:00, its own eight hours."""

    runtime = create_world(small_config(), seed=2024, world_id="world_one_night")
    agents = runtime.state.domain(AgentsState)
    clock = SimClock()

    runtime.kernel.run(SimClock.tick_at_hour(0, 20.0))
    person = next(p for p in agents.people.values() if p.tier is Tier.PERSISTENT and p.age_years > 25)

    slept_from = None
    woke_at = None
    for _ in range(int(TICKS_PER_DAY / TICKS_PER_HOUR)):
        runtime.kernel.run(TICKS_PER_HOUR)
        if person.activity is Activity.SLEEP and slept_from is None:
            slept_from = runtime.state.meta.tick
        elif slept_from is not None and person.activity is not Activity.SLEEP:
            woke_at = runtime.state.meta.tick
            break

    assert slept_from is not None, "the agent never went to sleep"
    assert woke_at is not None, "the agent never woke up"
    hours_asleep = (woke_at - slept_from) / TICKS_PER_HOUR
    assert 4.0 <= hours_asleep <= 12.0, f"slept {hours_asleep}h"
    assert clock.at(slept_from).hour >= 20 or clock.at(slept_from).hour <= 2


def test_sleeping_agents_are_skipped_entirely():
    """The core claim: a sleeping agent is not evaluated, not once, all night."""

    runtime = create_world(small_config(), seed=909, world_id="world_skip")
    agents = runtime.state.domain(AgentsState)
    brain = runtime.kernel.registry.get("agent_brains")

    evaluated: list[tuple[int, str, str]] = []
    original = brain.brain.decide

    def spy(view, rng):
        # Record the activity *at the moment of evaluation*, not at the end of the run.
        evaluated.append((view.tick, view.person_id, agents.people[view.person_id].activity.value))
        return original(view, rng)

    brain.brain.decide = spy

    runtime.kernel.run(SimClock.tick_at_hour(0, 22.0))
    evaluated.clear()

    # 22:00 → 07:00 the next morning.
    night_start = runtime.state.meta.tick
    runtime.kernel.run(TICKS_PER_DAY + SimClock.tick_at_hour(0, 7.0) - night_start)

    assert evaluated, "some agents are awake at night — night shifts exist"
    sleeping_evaluations = [row for row in evaluated if row[2] == Activity.SLEEP.value]
    assert not sleeping_evaluations, f"a sleeping agent was evaluated: {sleeping_evaluations[:3]}"


def test_night_costs_far_fewer_agent_ticks_than_daytime():
    runtime = create_world(small_config(), seed=1010, world_id="world_cost")
    from hydra.kernel.kernelstate import KernelDomainState

    def agent_ticks_over(hours: float) -> float:
        total = 0.0
        for _ in range(int(hours)):
            runtime.kernel.run(TICKS_PER_HOUR)
            total += runtime.state.domain(KernelDomainState).metrics.get("agent_ticks", 0.0)
        return total

    runtime.kernel.run(SimClock.tick_at_hour(0, 13.0))
    daytime = agent_ticks_over(4)             # 13:00 → 17:00
    runtime.kernel.run(SimClock.tick_at_hour(runtime.state.meta.tick, 1.0) + TICKS_PER_DAY - runtime.state.meta.tick)
    night = agent_ticks_over(4)               # 01:00 → 05:00

    assert night < daytime * 0.25, f"night should be far cheaper: day={daytime} night={night}"


def test_no_llm_call_is_made_while_asleep():
    """With a provider configured, sleeping agents still cost zero model calls."""

    config = small_config()
    config.llm.enabled = True
    runtime = create_world(config, seed=1111, world_id="world_llm")
    gateway = runtime.kernel.llm
    calls: list[tuple[int, str]] = []
    original = gateway.may_call

    def spy(person, importance, tick):
        calls.append((tick, person.person_id))
        return original(person, importance, tick)

    gateway.may_call = spy

    runtime.kernel.run(SimClock.tick_at_hour(0, 23.0))
    calls.clear()
    runtime.kernel.run(TICKS_PER_HOUR * 7)     # 23:00 → 06:00

    agents = runtime.state.domain(AgentsState)
    for _, person_id in calls:
        assert agents.people[person_id].activity is not Activity.SLEEP
    assert gateway.stats.calls == 0, "no provider is configured, so no call can have been made"


def test_wake_delivers_a_delta_summary_of_the_night():
    runtime = create_world(small_config(), seed=1212, world_id="world_delta")
    agents = runtime.state.domain(AgentsState)
    knowledge = runtime.state.domain(KnowledgeState)
    memory = runtime.state.domain(MemoryState)

    runtime.kernel.run(TICKS_PER_DAY + SimClock.tick_at_hour(0, 2.0))
    sleeper = next(p for p in agents.people.values() if p.activity is Activity.SLEEP and p.tier is Tier.PERSISTENT)

    # Something happens in the city while they are asleep.
    for index in range(3):
        knowledge.observe(
            sleeper.person_id,
            Observation(
                tick=runtime.state.meta.tick,
                kind="event",
                topic="env.power",
                summary="the power went out on your street",
                importance=0.4,
                source=Source.OBSERVED,
            ),
        )
    knowledge.observe(
        sleeper.person_id,
        Observation(
            tick=runtime.state.meta.tick,
            kind="message",
            topic="net.post",
            summary="a colleague messaged about the plant",
            importance=0.3,
            source=Source.SOCIAL,
        ),
    )

    wake_events: list = []
    runtime.kernel.bus.subscribe(["person.wake"], wake_events.append, "probe")

    # Advance hour by hour until this agent wakes, and look at its inbox at that moment —
    # an awake agent starts perceiving again immediately, so timing matters here.
    inbox_at_wake = None
    for _ in range(14):
        runtime.kernel.run(TICKS_PER_HOUR)
        if sleeper.activity is not Activity.SLEEP:
            inbox_at_wake = list(knowledge.inboxes.get(sleeper.person_id, []))
            break

    assert sleeper.activity is not Activity.SLEEP, "the agent never woke"
    assert inbox_at_wake is not None
    assert len(inbox_at_wake) <= 2, "the night's inbox is drained into the summary at wake"

    summaries = [
        item.summary
        for item in memory.for_person(sleeper.person_id).episodic + memory.for_person(sleeper.person_id).working
        if item.topic == "delta"
    ]
    assert any("During sleep" in text for text in summaries), summaries
    assert any(event.actor == sleeper.person_id for event in wake_events)


def test_schedule_is_stable_per_person():
    from hydra.kernel.config import DormancyConfig
    from hydra.kernel.rng import DeterministicRng

    runtime = create_world(small_config(), seed=1313, world_id="world_schedule")
    person = next(iter(runtime.state.domain(AgentsState).people.values()))
    config = DormancyConfig()
    first = schedule_for(person, config, DeterministicRng(42))
    second = schedule_for(person, config, DeterministicRng(42))
    assert first == second
    assert 0.0 <= first.sleep_hour < 24.0
    assert wake_tick_for(100, first) > 100
    assert should_sleep(person, first, first.sleep_hour + 0.1) or first.sleep_hour > first.wake_hour
