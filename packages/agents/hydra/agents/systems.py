"""Agent systems: perception, then decision.

Perception turns the objective world into *observations for this agent*. Decision turns an
agent's own view into an action intent. Between them there is a hard wall: the brain never
sees ``WorldState``.
"""

from __future__ import annotations

from hydra.companies.model import CompaniesState
from hydra.economy.model import EconomyState
from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics
from hydra.geography.model import GeographyState
from hydra.government.model import GovernmentState
from hydra.information.model import KnowledgeState, KnownFact, Observation, Source
from hydra.kernel.clock import TICKS_PER_HOUR
from hydra.kernel.systems import Phase, SystemSpec
from hydra.memory.model import MemoryState
from hydra.memory.operations import recall
from hydra.social.model import SocialState

from .brains import UtilityBrain, situation_importance
from .model import Activity, AgentsState, Employment, Person, Tier
from .view import AgentView, ViewFact, ViewOpening, ViewRelation

ESSENTIALS = ("food", "electricity", "housing", "transport")


class PerceptionSystem:
    """What an agent can notice from where it stands."""

    spec = SystemSpec(
        name="perception",
        phase=Phase.AGENTS,
        cadence_ticks=TICKS_PER_HOUR,
        priority=10,
        reads=("agents", "geography", "economy", "information", "companies"),
        writes=("information", "agents"),
        emits=(),
        description="Builds per-agent observations from local, observable conditions only.",
    )

    def __init__(self, cadence_ticks: int = TICKS_PER_HOUR) -> None:
        self.spec = PerceptionSystem.spec.with_cadence(cadence_ticks)

    def step(self, ctx) -> None:  # noqa: ANN001
        agents = ctx.state.domain(AgentsState)
        geography = ctx.state.domain(GeographyState)
        economy = ctx.state.domain(EconomyState)
        knowledge = ctx.state.domain(KnowledgeState)
        companies = ctx.state.domain(CompaniesState)
        limit = ctx.config.agents.perception_batch
        seen = 0

        for person_id in sorted(agents.people):
            person = agents.people[person_id]
            if not person.alive or person.activity in (Activity.SLEEP, Activity.OFFSCREEN):
                continue
            if seen >= limit:
                break
            seen += 1
            district = geography.districts.get(person.district_id)
            if district is None:
                continue

            # A blackout is not something you read about; you sit in the dark.
            if district.power_reliability < 0.97:
                knowledge.observe(
                    person.person_id,
                    Observation(
                        tick=ctx.tick,
                        kind="event",
                        topic="env.power",
                        summary=f"power is unreliable in {district.name}",
                        importance=round(min(0.9, (1.0 - district.power_reliability) * 2.2), 4),
                        source=Source.OBSERVED,
                    ),
                )
                person.needs.safety = round(max(0.0, person.needs.safety - 0.02), 4)

            if district.unrest > 0.25:
                knowledge.observe(
                    person.person_id,
                    Observation(
                        tick=ctx.tick,
                        kind="event",
                        topic="social.unrest",
                        summary=f"tension on the streets of {district.name}",
                        importance=round(min(0.8, district.unrest), 4),
                        source=Source.OBSERVED,
                    ),
                )

            if person.employer_id:
                company = companies.companies.get(person.employer_id)
                if company is not None and company.months_of_loss >= 2:
                    fact_id = f"fact_company_{company.company_id}_stress"
                    if fact_id not in knowledge.facts:
                        from hydra.information.model import Fact

                        knowledge.add_fact(
                            Fact(
                                fact_id=fact_id,
                                tick=ctx.tick,
                                topic="company.trouble",
                                subject=company.company_id,
                                claim="losing_money",
                                value=float(company.months_of_loss),
                                text=f"{company.name} has been losing money",
                                district_id=company.district_id,
                                importance=0.4,
                            )
                        )
                    knowledge.learn(
                        person.person_id,
                        KnownFact(fact_id=fact_id, acquired_tick=ctx.tick, source=Source.WORK,
                                  confidence=0.7, value=float(company.months_of_loss)),
                    )
                    knowledge.observe(
                        person.person_id,
                        Observation(
                            tick=ctx.tick,
                            kind="fact",
                            topic="company.trouble",
                            summary=f"talk of trouble at {company.name}",
                            importance=0.45,
                            fact_id=fact_id,
                            source=Source.WORK,
                        ),
                    )

            # Prices are learned by paying them; here we only refresh what they already track.
            if ctx.now.hour in (9, 18):
                for code in ESSENTIALS:
                    fact_id = f"fact_genesis_price_{code}"
                    known = knowledge.known(person.person_id).get(fact_id)
                    if known is None:
                        continue
                    observed = float(economy.markets[code].price_minor)
                    if abs(observed - known.value) / max(1.0, known.value) > 0.05:
                        known.value = round(0.5 * known.value + 0.5 * observed, 3)
                        known.acquired_tick = ctx.tick
                        known.confidence = round(min(1.0, known.confidence + 0.05), 4)
                        knowledge.observe(
                            person.person_id,
                            Observation(
                                tick=ctx.tick,
                                kind="fact",
                                topic=f"price.{code}",
                                summary=f"{code} costs {observed / 100:.2f} now",
                                importance=0.3 if code in ("food", "electricity") else 0.15,
                                fact_id=fact_id,
                                source=Source.OBSERVED,
                            ),
                        )
        ctx.telemetry.gauge("perceptions", float(seen))


class AgentBrainSystem:
    """Runs brains for the agents that matter this tick, within a fixed compute budget."""

    spec = SystemSpec(
        name="agent_brains",
        phase=Phase.AGENTS,
        cadence_ticks=TICKS_PER_HOUR,
        priority=20,
        reads=("agents", "information", "memory", "social", "economy", "companies", "geography", "government"),
        writes=("agents", "information", "memory", "social", "economy", "companies", "geography", "government", "net"),
        emits=(Topics.PERSON_ACTION, Topics.PERSON_PROMOTED_TIER),
        description="Utility-AI decisions with optional, budgeted LLM escalation for Tier A.",
    )

    def __init__(self, cadence_ticks: int = TICKS_PER_HOUR, brain: UtilityBrain | None = None) -> None:
        self.spec = AgentBrainSystem.spec.with_cadence(cadence_ticks)
        self.brain = brain or UtilityBrain()

    def step(self, ctx) -> None:  # noqa: ANN001
        agents = ctx.state.domain(AgentsState)
        config = ctx.config.agents
        candidates = [
            p for p in agents.people.values()
            if p.alive and p.activity is Activity.ACTIVE and p.age_years >= 14
        ]
        # Priority queue: persistent agents first, then whoever has most at stake.
        candidates.sort(
            key=lambda p: (
                0 if p.tier is Tier.PERSISTENT else 1,
                -(p.importance + p.stress * 0.4 + (0.5 if not p.employer_id else 0.0)),
                p.person_id,
            )
        )
        budget = config.max_brain_evaluations_per_tick
        evaluations = 0
        llm_calls = 0

        for person in candidates[:budget]:
            view = build_view(ctx, person)
            rng = ctx.rng("brain", person.person_id)
            importance = situation_importance(view)
            view.salience = importance
            intent = None
            gateway = ctx.llm
            if gateway is not None and getattr(gateway, "enabled", False):
                model = gateway.may_call(person, importance, ctx.tick)
                if model:
                    allowed = [option.action for option in self.brain.options(view)]
                    intent = gateway.propose(person, view, allowed, model)
                    if intent is not None:
                        llm_calls += 1
            if intent is None:
                intent = self.brain.decide(view, rng)
            if intent is None:
                continue
            evaluations += 1
            result = ctx.submit(intent)
            if result.accepted:
                person.last_active_tick = ctx.tick
                self._maybe_promote(ctx, person, agents, importance)

        ctx.telemetry.gauge("agent_ticks", float(evaluations))
        ctx.telemetry.incr("llm_calls", float(llm_calls))
        if ctx.llm is not None:
            ctx.telemetry.gauge("tokens_used", float(getattr(ctx.llm, "stats", None).tokens if getattr(ctx.llm, "stats", None) else 0))

    def _maybe_promote(self, ctx, person: Person, agents: AgentsState, importance: float) -> None:  # noqa: ANN001
        """COHORT/Tier B → persistent individual, when someone starts to matter."""

        if person.tier is Tier.PERSISTENT:
            return
        if importance < ctx.config.agents.promotion_importance:
            return
        person.tier = Tier.PERSISTENT
        person.importance = round(max(person.importance, importance), 4)
        person.compute.llm_calls_per_day = ctx.config.llm.daily_calls_per_agent
        person.compute.token_budget = ctx.config.llm.token_budget_per_agent
        agents.persistent_ids.append(person.person_id)
        if person.person_id in agents.lightweight_ids:
            agents.lightweight_ids.remove(person.person_id)
        agents.promotions += 1
        ctx.emit(
            Topics.PERSON_PROMOTED_TIER,
            "became_significant",
            actor=person.person_id,
            location=person.district_id,
            payload={"importance": person.importance, "occupation": person.occupation},
            inputs=ImportanceInputs(people_affected=1, novelty=0.7, proximity=1.0),
        )


def build_view(ctx, person: Person) -> AgentView:  # noqa: ANN001
    """Assemble the agent's subjective picture. This is the only bridge from world to brain."""

    knowledge = ctx.state.domain(KnowledgeState)
    memory = ctx.state.domain(MemoryState)
    social = ctx.state.domain(SocialState)
    economy = ctx.state.domain(EconomyState)
    companies = ctx.state.domain(CompaniesState)
    geography = ctx.state.domain(GeographyState)
    government = ctx.state.domain(GovernmentState)

    known = knowledge.known(person.person_id)
    facts: list[ViewFact] = []
    perceived_prices: dict[str, float] = {}
    for fact_id, known_fact in sorted(known.items(), key=lambda kv: -kv[1].confidence)[:16]:
        fact = knowledge.facts.get(fact_id)
        topic = fact.topic if fact else "unknown"
        facts.append(
            ViewFact(
                fact_id=fact_id,
                topic=topic,
                value=known_fact.value,
                confidence=known_fact.confidence,
                source=known_fact.source.value,
                acquired_tick=known_fact.acquired_tick,
                text=fact.text if fact else "",
            )
        )
        if topic.startswith("price."):
            perceived_prices[topic.split(".", 1)[1]] = known_fact.value

    inbox = knowledge.inboxes.get(person.person_id, [])
    district = geography.districts.get(person.district_id)
    relations = [
        ViewRelation(person_id=e.target, relation=e.relation.value, trust=e.trust,
                     sentiment=e.sentiment, strength=e.strength)
        for e in social.neighbours(person.person_id)[:12]
    ]
    openings = [
        ViewOpening(
            opening_id=o.opening_id,
            company_id=o.company_id,
            role=o.role,
            wage_minor=o.wage_minor,
            skill=o.skill,
            skill_required=o.skill_required,
        )
        for o in companies.openings.values()
        if o.positions > o.filled
        and companies.companies.get(o.company_id)
        and companies.companies[o.company_id].district_id == person.district_id
    ][:5]

    return AgentView(
        person_id=person.person_id,
        name=person.name,
        tier=person.tier.value,
        tick=ctx.tick,
        hour=ctx.now.hour,
        age_years=person.age_years,
        district_id=person.district_id,
        location_building_id=person.location_building_id,
        occupation=person.occupation,
        employer_id=person.employer_id,
        employed=person.employment in (Employment.EMPLOYED, Employment.PUBLIC, Employment.SELF_EMPLOYED),
        wage_minor=person.wage_minor,
        balance_minor=economy.balance(person.account_id),
        energy=person.energy,
        stress=person.stress,
        mood=person.mood,
        health=person.health,
        political_trust=person.political_trust,
        needs={
            "food": person.needs.food,
            "rest": person.needs.rest,
            "safety": person.needs.safety,
            "social": person.needs.social,
            "esteem": person.needs.esteem,
            "purpose": person.needs.purpose,
        },
        personality={
            "openness": person.personality.openness,
            "conscientiousness": person.personality.conscientiousness,
            "extraversion": person.personality.extraversion,
            "agreeableness": person.personality.agreeableness,
            "neuroticism": person.personality.neuroticism,
            "risk_tolerance": person.personality.risk_tolerance,
            "ambition": person.personality.ambition,
        },
        goals=[g.label for g in person.goals],
        known_facts=facts,
        beliefs={t: b.position for t, b in list(knowledge.beliefs.get(person.person_id, {}).items())[:8]},
        inbox=[o.summary for o in inbox[-6:]],
        inbox_importance=max((o.importance for o in inbox), default=0.0),
        memories=[m.summary for m in recall(memory.for_person(person.person_id), "", ctx.tick, limit=4)],
        relations=relations,
        openings=openings,
        perceived_prices=perceived_prices,
        perceived_power_reliability=district.power_reliability if district else 1.0,
        perceived_unrest=district.unrest if district else 0.0,
        situation="strained" if person.stress > 0.6 or not person.employer_id else "routine",
    )
