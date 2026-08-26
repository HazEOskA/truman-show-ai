"""Culture engine.

Trends are not rolled from a table: each one is born out of a condition the city is actually
living through — a blackout, a wave of layoffs, a price spike, a long quiet spell — and it
carries a pointer back to the event that produced it.
"""

from __future__ import annotations

from hydra.agents.model import AgentsState
from hydra.economy.model import EconomyState
from hydra.events.model import Topics
from hydra.geography.model import GeographyState
from hydra.government.model import GovernmentState
from hydra.information.model import KnowledgeState
from hydra.kernel.clock import TICKS_PER_DAY
from hydra.kernel.systems import Phase, SystemSpec

from .model import CultureState, Trend, TrendKind

# condition -> (kind, label template, sentiment)
SEEDS: tuple[tuple[str, TrendKind, str, float], ...] = (
    ("blackout", TrendKind.SLANG, "candlelight shift", -0.4),
    ("blackout", TrendKind.MEME, "the grid is a suggestion", -0.5),
    ("layoffs", TrendKind.MOVEMENT, "Union of the Let Go", -0.6),
    ("layoffs", TrendKind.MUSIC, "severance blues", -0.5),
    ("prices", TrendKind.SLANG, "paying hydra prices", -0.45),
    ("prices", TrendKind.CONSPIRACY, "the meter reads twice", -0.7),
    ("unrest", TrendKind.SUBCULTURE, "the Verge collective", -0.3),
    ("unrest", TrendKind.IDEOLOGY, "municipalism", 0.1),
    ("calm", TrendKind.FASHION, "long coats and quiet", 0.35),
    ("calm", TrendKind.ART, "rooftop light murals", 0.5),
    ("growth", TrendKind.LEGEND, "the second founding", 0.6),
)


class CultureSystem:
    spec = SystemSpec(
        name="culture",
        phase=Phase.SLOW,
        cadence_ticks=TICKS_PER_DAY * 7,
        priority=30,
        reads=("culture", "agents", "economy", "government", "geography", "information"),
        writes=("culture",),
        emits=(Topics.CULTURE_TREND,),
        description="Emergent slang, memes, movements and conspiracies driven by lived conditions.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        culture = ctx.state.domain(CultureState)
        agents = ctx.state.domain(AgentsState)
        economy = ctx.state.domain(EconomyState)
        government = ctx.state.domain(GovernmentState)
        geography = ctx.state.domain(GeographyState)
        knowledge = ctx.state.domain(KnowledgeState)
        rng = ctx.rng("culture")

        city = geography.city()
        reliability = min(1.0, city.infrastructure.power_output_mw / max(1e-6, city.infrastructure.power_demand_mw))
        condition_weights = {
            "blackout": max(0.0, 1.0 - reliability) * 3.0,
            "layoffs": min(1.5, economy.unemployment_rate * 6.0),
            "prices": min(1.5, max(0.0, economy.inflation_annual) * 4.0),
            "unrest": min(1.5, government.unrest_index * 4.0),
            "calm": max(0.0, 1.2 - government.unrest_index * 5.0 - economy.unemployment_rate * 4.0),
            "growth": max(0.0, (0.06 - economy.unemployment_rate) * 8.0),
        }
        conditions = sorted(condition_weights)
        weights = [condition_weights[c] for c in conditions]

        population = max(1, agents.cohort_population())
        mood = sum(c.sentiment * c.size for c in agents.cohorts.values()) / population
        culture.mood_index = round(mood, 5)

        if sum(weights) > 0.4 and rng.chance(min(0.9, sum(weights) * 0.35)):
            condition = rng.weighted_choice(conditions, weights)
            options = [s for s in SEEDS if s[0] == condition]
            if options:
                _, kind, label, sentiment = rng.choice(options)
                if not any(t.label == label and t.dead_tick is None for t in culture.trends.values()):
                    culture.next_trend_index += 1
                    district = rng.choice(sorted(geography.districts))
                    recent = sorted(knowledge.facts.values(), key=lambda f: (-f.tick, f.fact_id))[:1]
                    trend = Trend(
                        trend_id=f"trend_{culture.next_trend_index:05d}",
                        kind=kind,
                        label=label,
                        origin_district_id=district,
                        birth_tick=ctx.tick,
                        driver_topic=condition,
                        driver_event_id=recent[0].origin_event_id if recent else "",
                        popularity=round(rng.uniform(0.02, 0.08), 4),
                        momentum=round(condition_weights[condition] * rng.uniform(0.02, 0.06), 4),
                        sentiment=sentiment,
                    )
                    culture.trends[trend.trend_id] = trend
                    culture.born_total += 1
                    if kind is TrendKind.SLANG:
                        culture.slang[label] = condition
                    ctx.emit(
                        Topics.CULTURE_TREND,
                        "trend_emerged",
                        target=trend.trend_id,
                        location=district,
                        payload={"label": label, "kind": kind.value, "driver": condition},
                        importance=0.25,
                    )

        for trend in list(culture.trends.values()):
            if trend.dead_tick is not None:
                continue
            drift = condition_weights.get(trend.driver_topic, 0.0) * 0.05 - 0.012
            trend.popularity = round(max(0.0, min(1.0, trend.popularity + trend.momentum + drift)), 5)
            trend.momentum = round(trend.momentum * 0.85, 5)
            trend.peak_popularity = max(trend.peak_popularity, trend.popularity)
            trend.adherents = int(agents.total_population() * trend.popularity)
            if trend.popularity <= 0.005 and ctx.tick - trend.birth_tick > TICKS_PER_DAY * 30:
                trend.dead_tick = ctx.tick
                culture.died_total += 1

        ctx.telemetry.gauge("culture_trends", float(len(culture.alive())))
        ctx.telemetry.gauge("culture_mood", culture.mood_index)
