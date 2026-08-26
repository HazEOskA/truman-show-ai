"""Information systems: facts, propagation and belief.

Rule: nobody is ever informed straight from world state. A system makes something true, the
fact system records it as an objective fact, and only then can it travel — through media, the
net, conversation or direct observation — with a source, a delay and a chance of distortion.
"""

from __future__ import annotations

from hydra.agents.model import Activity, AgentsState
from hydra.events.model import Event, Topics, Visibility
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR
from hydra.kernel.ids import fact_id as make_fact_id
from hydra.kernel.systems import Phase, SystemSpec

from .model import Fact, KnowledgeState, KnownFact, Observation, Source
from .net import NetState
from .rendering import render_fact

FACT_THRESHOLD = 0.28
MAX_MOOD_SHIFT_PER_CYCLE = 0.05
NEGATIVE_TOPICS = (
    "company.layoff", "company.bankrupt", "market.shortage", "env.power.shortage",
    "person.protest", "gov.emergency", "bank.default",
)
POSITIVE_TOPICS = (
    "company.founded", "company.hire", "tech.discovery", "tech.adoption", "gov.policy",
)


class FactSystem:
    """Turns significant, observable events into objective facts about the world."""

    spec = SystemSpec(
        name="facts",
        phase=Phase.INFORMATION,
        cadence_ticks=0,
        priority=5,
        reads=("information",),
        writes=("information",),
        consumes=("market.*", "env.*", "company.*", "gov.*", "person.protest", "person.death",
                  "tech.discovery", "bank.default"),
        description="Event → objective Fact, with deterministic rendering and no LLM.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        return

    def on_event(self, ctx, event: Event) -> None:  # noqa: ANN001
        if event.importance < FACT_THRESHOLD or event.visibility in (Visibility.HIDDEN, Visibility.PRIVATE):
            return
        knowledge = ctx.state.domain(KnowledgeState)
        claim, text, value = render_fact(event)
        fact_id = make_fact_id(ctx.state.next_fact_seq())
        knowledge.add_fact(
            Fact(
                fact_id=fact_id,
                tick=ctx.tick,
                topic=event.topic,
                subject=event.actor or event.target or event.location or "city",
                claim=claim,
                value=value,
                text=text,
                district_id=event.location or "",
                importance=event.importance,
                origin_event_id=event.event_id,
                truth=event.truth,
            )
        )


class PropagationSystem:
    """Moves information through the population: net posts, word of mouth, cohort awareness."""

    spec = SystemSpec(
        name="propagation",
        phase=Phase.INFORMATION,
        cadence_ticks=TICKS_PER_HOUR,
        priority=30,
        reads=("information", "net", "agents", "media"),
        writes=("information", "net", "agents"),
        emits=(Topics.INFO_SPREAD,),
        description="Diffusion of facts to individuals and cohorts, with decay and distortion.",
    )

    def __init__(self, cadence_ticks: int = TICKS_PER_HOUR) -> None:
        self.spec = PropagationSystem.spec.with_cadence(cadence_ticks)

    def step(self, ctx) -> None:  # noqa: ANN001
        knowledge = ctx.state.domain(KnowledgeState)
        net = ctx.state.domain(NetState)
        agents = ctx.state.domain(AgentsState)
        config = ctx.config.information
        rng = ctx.rng("propagation")
        horizon = ctx.tick - TICKS_PER_DAY * 2

        recent_facts = [f for f in knowledge.facts.values() if f.tick >= horizon and f.importance >= 0.3]
        recent_facts.sort(key=lambda f: (-f.importance, f.fact_id))
        recent_facts = recent_facts[:40]

        # 1. HydraNet posts reach a sample of readers in the author's reach.
        fresh_posts = [p for p in net.posts.values() if p.tick >= ctx.tick - self.spec.cadence_ticks]
        awake = [
            p.person_id for p in agents.people.values()
            if p.alive and p.activity in (Activity.ACTIVE, Activity.LIGHT_IDLE)
        ]
        awake.sort()
        delivered = 0
        for post in sorted(fresh_posts, key=lambda p: p.post_id):
            if not awake or not post.fact_id:
                continue
            audience = min(len(awake), max(1, int(post.reach / 120)))
            for reader_id in rng.sample(awake, min(audience, 10)):
                if reader_id == post.author_id or knowledge.knows(reader_id, post.fact_id):
                    continue
                fact = knowledge.facts.get(post.fact_id)
                knowledge.learn(
                    reader_id,
                    KnownFact(
                        fact_id=post.fact_id,
                        acquired_tick=ctx.tick,
                        source=Source.SEARCH if post.site_id == "site_search" else Source.SOCIAL,
                        confidence=round(0.25 + net.sites[post.site_id].trust * 0.4, 4),
                        value=fact.value if fact else 0.0,
                        via=post.site_id,
                    ),
                )
                knowledge.observe(
                    reader_id,
                    Observation(
                        tick=ctx.tick,
                        kind="fact",
                        topic=post.topic,
                        summary=post.text,
                        importance=fact.importance * 0.6 if fact else 0.2,
                        fact_id=post.fact_id,
                        source=Source.SOCIAL,
                        via=post.site_id,
                    ),
                )
                post.engagement += 1
                delivered += 1
        knowledge.spread_events += delivered

        # 2. Cohorts absorb information as an awareness share, not as individual messages.
        moved: dict[str, float] = {}
        for fact in recent_facts:
            for cohort_id in sorted(agents.cohorts):
                cohort = agents.cohorts[cohort_id]
                awareness = knowledge.cohort_awareness.setdefault(cohort_id, {})
                current = awareness.get(fact.fact_id, 0.0)
                local = 1.0 if (not fact.district_id or fact.district_id == cohort.district_id) else 0.35
                pressure = (fact.importance * 0.55 + config.social_share_probability) * local
                new_awareness = current + (1.0 - current) * min(0.9, pressure)
                awareness[fact.fact_id] = round(new_awareness, 5)
                gained = new_awareness - current
                if gained <= 0.01 or fact.importance < 0.4:
                    continue
                sign = 0.0
                if fact.topic in NEGATIVE_TOPICS:
                    sign = -1.0
                elif fact.topic in POSITIVE_TOPICS:
                    sign = 1.0
                if sign == 0.0:
                    continue
                # News moves how a neighbourhood feels, but it does not *set* it: the
                # pressure below decays, and living standards still decide the baseline.
                budget = max(0.0, MAX_MOOD_SHIFT_PER_CYCLE - moved.get(cohort_id, 0.0))
                weight = min(budget, gained * fact.importance * 0.5)
                if weight <= 0.0:
                    continue
                moved[cohort_id] = moved.get(cohort_id, 0.0) + weight
                cohort.news_pressure = round(max(-1.0, min(1.0, cohort.news_pressure + sign * weight)), 5)
                if len(awareness) > 120:
                    for key in sorted(awareness, key=lambda k: awareness[k])[: len(awareness) - 120]:
                        del awareness[key]

        # 3. Old news fades.
        for cohort_id in sorted(knowledge.cohort_awareness):
            awareness = knowledge.cohort_awareness[cohort_id]
            for fact_id in list(awareness):
                fact = knowledge.facts.get(fact_id)
                if fact is None or fact.tick < ctx.tick - TICKS_PER_DAY * 20:
                    del awareness[fact_id]
                else:
                    awareness[fact_id] = round(awareness[fact_id] * 0.995, 5)

        if delivered:
            ctx.emit(
                Topics.INFO_SPREAD,
                "information_spread",
                payload={"deliveries": delivered, "facts_live": len(recent_facts)},
                importance=0.03,
                visibility=Visibility.HIDDEN,
            )
        ctx.telemetry.gauge("facts_known", float(len(knowledge.facts)))
        ctx.telemetry.gauge("info_deliveries", float(delivered))
