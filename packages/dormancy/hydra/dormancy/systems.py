"""Dormancy system: the world's compute governor.

Every tick it decides who is worth simulating. Sleeping agents are skipped outright, dormant
agents are advanced statistically, and only agents with something at stake are marked ACTIVE
and handed to a brain.
"""

from __future__ import annotations

from hydra.agents.model import Activity, AgentsState, Tier
from hydra.events.model import Event, Topics, Visibility
from hydra.information.model import KnowledgeState
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR
from hydra.kernel.systems import Phase, SystemSpec
from hydra.memory.model import MemoryKind, MemoryState
from hydra.memory.operations import consolidate, record as record_memory

from .engine import (
    DeltaSummary,
    apply_sleep_recovery,
    idle_decay,
    next_activity,
    schedule_for,
    should_sleep,
    wake_reason,
    wake_tick_for,
)


class DormancySystem:
    spec = SystemSpec(
        name="dormancy",
        phase=Phase.AGENTS,
        cadence_ticks=TICKS_PER_HOUR,
        priority=5,
        reads=("agents", "information", "memory"),
        writes=("agents", "memory", "information"),
        emits=(Topics.PERSON_SLEEP, Topics.PERSON_WAKE),
        consumes=("company.layoff", "person.job_lost", "env.power.shortage", "gov.emergency", "net.post"),
        description="ACTIVE/LIGHT_IDLE/SLEEP/DORMANT/OFFSCREEN lifecycle, sleep skip and wake deltas.",
    )

    def __init__(self, cadence_ticks: int = TICKS_PER_HOUR) -> None:
        self.spec = DormancySystem.spec.with_cadence(cadence_ticks)

    def step(self, ctx) -> None:  # noqa: ANN001
        agents = ctx.state.domain(AgentsState)
        knowledge = ctx.state.domain(KnowledgeState)
        memory = ctx.state.domain(MemoryState)
        config = ctx.config.dormancy
        info_config = ctx.config.information
        hour = ctx.now.hour + ctx.now.minute / 60.0
        hours_elapsed = self.spec.cadence_ticks / TICKS_PER_HOUR

        counts = {state.value: 0 for state in Activity}
        for person_id in sorted(agents.people):
            person = agents.people[person_id]
            if not person.alive:
                continue

            if person.activity is Activity.SLEEP:
                if ctx.tick < person.wake_tick:
                    counts[Activity.SLEEP.value] += 1
                    continue                       # the skip: no reasoning, no LLM, no cost
                self._wake(ctx, person, knowledge, memory, agents, reason="scheduled")
                counts[person.activity.value] += 1
                continue

            schedule = schedule_for(person, config, ctx.stable_rng("sleep", person_id))
            if person.age_years >= 3 and should_sleep(person, schedule, hour):
                self._sleep(ctx, person, schedule, memory, info_config)
                counts[Activity.SLEEP.value] += 1
                continue

            idle_decay(person, hours_elapsed)
            inbox = knowledge.inboxes.get(person_id, [])
            salience = max((o.importance for o in inbox), default=0.0)
            if person.employer_id and 8 <= ctx.now.hour <= 17:
                salience = max(salience, 0.25)
            if person.needs.food < 0.4 or person.energy < 0.35:
                salience = max(salience, 0.4)
            previous = person.activity
            person.activity = next_activity(person, salience, config)
            if person.activity is Activity.ACTIVE:
                person.idle_days = 0.0
                person.last_active_tick = ctx.tick
            else:
                person.idle_days = round(person.idle_days + hours_elapsed / 24.0, 4)
            if previous is not person.activity:
                person.activity_since_tick = ctx.tick
            counts[person.activity.value] += 1

        agents.activity_counts = counts
        ctx.telemetry.gauge("active_agents", float(counts[Activity.ACTIVE.value]))
        ctx.telemetry.gauge("light_idle_agents", float(counts[Activity.LIGHT_IDLE.value]))
        ctx.telemetry.gauge("sleeping_agents", float(counts[Activity.SLEEP.value]))
        ctx.telemetry.gauge("dormant_agents", float(counts[Activity.DORMANT.value]))
        ctx.telemetry.gauge("population_individuals", float(len(agents.people)))
        ctx.telemetry.gauge("population_total", float(agents.total_population()))

    # -- transitions --------------------------------------------------------------
    def _sleep(self, ctx, person, schedule, memory: MemoryState, info_config) -> None:  # noqa: ANN001
        person.activity = Activity.SLEEP
        person.activity_since_tick = ctx.tick
        person.sleep_started_tick = ctx.tick
        person.wake_tick = wake_tick_for(ctx.tick, schedule)
        # Memory consolidation happens during sleep, not while awake.
        consolidate(
            memory.for_person(person.person_id),
            ctx.tick,
            episodic_limit=info_config.max_episodic_memory,
            per_day_decay=info_config.memory_decay_per_day,
        )
        memory.consolidations += 1
        if person.tier is Tier.PERSISTENT:
            ctx.emit(
                Topics.PERSON_SLEEP,
                "fell_asleep",
                actor=person.person_id,
                location=person.district_id,
                payload={"wake_tick": person.wake_tick},
                importance=0.01,
                visibility=Visibility.PRIVATE,
            )

    def _wake(self, ctx, person, knowledge: KnowledgeState, memory: MemoryState, agents: AgentsState, *, reason: str) -> None:  # noqa: ANN001
        slept = max(0, ctx.tick - max(0, person.sleep_started_tick))
        apply_sleep_recovery(person, slept)
        summary = self._delta_summary(person.person_id, knowledge, person.sleep_started_tick, ctx.tick)
        person.activity = Activity.ACTIVE
        person.activity_since_tick = ctx.tick
        person.sleep_started_tick = -1
        person.last_active_tick = ctx.tick
        person.idle_days = 0.0

        if summary.items:
            record_memory(
                memory,
                person.person_id,
                tick=ctx.tick,
                topic="delta",
                summary=summary.text(),
                kind=MemoryKind.EPISODIC,
                salience=min(0.9, 0.3 + summary.top_importance),
                source="delta_summary",
                working_limit=ctx.config.information.max_working_memory,
            )
        if person.tier is Tier.PERSISTENT or summary.top_importance > 0.5:
            ctx.emit(
                Topics.PERSON_WAKE,
                "woke_up",
                actor=person.person_id,
                location=person.district_id,
                payload={
                    "reason": reason,
                    "slept_ticks": slept,
                    "delta": summary.text(),
                    "delta_items": len(summary.items),
                },
                importance=0.02 + summary.top_importance * 0.1,
                visibility=Visibility.PRIVATE,
            )

    @staticmethod
    def _delta_summary(person_id: str, knowledge: KnowledgeState, from_tick: int, to_tick: int) -> DeltaSummary:
        """Built from the agent's own inbox — never from global state."""

        observations = knowledge.drain_inbox(person_id)
        summary = DeltaSummary(person_id=person_id, from_tick=from_tick, to_tick=to_tick)
        grouped: dict[str, list] = {}
        for observation in observations:
            grouped.setdefault(observation.topic, []).append(observation)
            summary.top_importance = max(summary.top_importance, observation.importance)
            if observation.kind == "message":
                summary.messages += 1
        for topic in sorted(grouped):
            items = grouped[topic]
            summary.topics[topic] = len(items)
            best = max(items, key=lambda o: o.importance)
            summary.items.append(f"{best.summary}" + (f" (×{len(items)})" if len(items) > 1 else ""))
        return summary

    # -- event driven wake --------------------------------------------------------
    def on_event(self, ctx, event: Event) -> None:  # noqa: ANN001
        config = ctx.config.dormancy
        if event.importance < config.wake_importance_threshold * 0.6:
            return
        agents = ctx.state.domain(AgentsState)
        knowledge = ctx.state.domain(KnowledgeState)
        memory = ctx.state.domain(MemoryState)

        personal_ids = [i for i in (event.actor, event.target) if i and i.startswith("person_")]
        for person_id in personal_ids:
            person = agents.people.get(person_id)
            if person is None or not person.alive:
                continue
            reason = wake_reason(event.importance, True, config)
            if not reason:
                continue
            if person.activity is Activity.SLEEP and event.importance < 0.8:
                continue                  # only genuine danger wakes someone at night
            if person.activity in (Activity.SLEEP, Activity.DORMANT, Activity.OFFSCREEN):
                self._wake(ctx, person, knowledge, memory, agents, reason=reason)
                ctx.telemetry.incr("event_wakeups")
