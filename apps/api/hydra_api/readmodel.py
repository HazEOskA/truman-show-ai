"""Read model: world state → the JSON the Observatory renders.

The Observatory is read-first (spec section 25), so this module is deliberately one-way. It
never mutates a world; it projects one. Every view here answers a question an operator would
actually ask while watching a city run.
"""

from __future__ import annotations

from typing import Any

from hydra.agents.model import Activity, AgentsState, Tier
from hydra.companies.model import CompaniesState
from hydra.culture.model import CultureState
from hydra.economy.model import EconomyState
from hydra.geography.model import BuildingKind, GeographyState
from hydra.government.model import GovernmentState
from hydra.history.state import HistoryState
from hydra.information.model import KnowledgeState
from hydra.information.net import NetState
from hydra.kernel.clock import TICKS_PER_DAY, SimClock
from hydra.kernel.kernelstate import KernelDomainState
from hydra.kernel.state import WorldState
from hydra.media.model import MediaState
from hydra.memory.model import MemoryState
from hydra.population.model import PopulationState
from hydra.social.model import SocialState
from hydra.technology.model import TechnologyState


def money(minor: int) -> float:
    return round(minor / 100.0, 2)


def world_summary(state: WorldState) -> dict[str, Any]:
    clock = SimClock()
    now = clock.at(state.meta.tick)
    agents = state.domain(AgentsState)
    economy = state.domain(EconomyState)
    companies = state.domain(CompaniesState)
    government = state.domain(GovernmentState)
    geography = state.domain(GeographyState)
    kernel_state = state.domain(KernelDomainState)
    city = geography.city()
    return {
        "world_id": state.meta.world_id,
        "timeline_id": state.meta.timeline_id,
        "parent_timeline_id": state.meta.parent_timeline_id,
        "fork_tick": state.meta.fork_tick,
        "seed": state.meta.seed,
        "kernel_version": state.meta.kernel_version,
        "config_hash": state.meta.config_hash,
        "phase": state.meta.phase.value,
        "tick": state.meta.tick,
        "day": state.meta.tick // TICKS_PER_DAY,
        "sim_time": now.label(),
        "state_hash": state.state_hash(),
        "population": agents.total_population(),
        "individuals": len(agents.people),
        "persistent_agents": len(agents.persistent_ids),
        "cohorts": len(agents.cohorts),
        "companies": len(companies.active()),
        "city": {
            "name": city.name,
            "districts": len(city.district_ids),
            "power_capacity_mw": city.infrastructure.power_capacity_mw,
            "power_output_mw": city.infrastructure.power_output_mw,
            "power_demand_mw": city.infrastructure.power_demand_mw,
        },
        "economy": {
            "cpi": economy.cpi,
            "inflation_annual": economy.inflation_annual,
            "unemployment": economy.unemployment_rate,
            "energy_price": economy.markets["electricity"].price_minor,
            "wage_index": economy.wage_index,
        },
        "government": {
            "approval": government.approval,
            "unrest": government.unrest_index,
            "emergency_level": government.emergency_level,
            "active_policies": len(government.active_policies()),
        },
        "metrics": kernel_state.metrics,
        "activity": agents.activity_counts,
    }


def metrics_view(state: WorldState) -> dict[str, Any]:
    kernel_state = state.domain(KernelDomainState)
    economy = state.domain(EconomyState)
    agents = state.domain(AgentsState)
    companies = state.domain(CompaniesState)
    government = state.domain(GovernmentState)
    metrics = dict(kernel_state.metrics)
    metrics.update(
        {
            "world_tick": float(state.meta.tick),
            "population": float(agents.total_population()),
            "companies": float(len(companies.active())),
            "gdp_minor": float(economy.gdp_minor),
            "unemployment": economy.unemployment_rate,
            "inflation": economy.inflation_annual,
            "cpi": economy.cpi,
            "energy_price": float(economy.markets["electricity"].price_minor),
            "approval": government.approval,
            "unrest": government.unrest_index,
            "imports_minor": float(economy.imports_minor),
            "exports_minor": float(economy.exports_minor),
            "money_supply_minor": float(economy.money_supply_minor),
        }
    )
    return {
        "tick": state.meta.tick,
        "metrics": {k: round(float(v), 6) for k, v in sorted(metrics.items())},
        "system_health": {
            name: {"failures": h.failures, "quarantined": h.quarantined, "last_error": h.last_error}
            for name, h in sorted(kernel_state.health.items())
            if h.failures
        },
    }


def city_view(state: WorldState) -> dict[str, Any]:
    geography = state.domain(GeographyState)
    population = state.domain(PopulationState)
    city = geography.city()
    region = geography.regions[city.region_id]
    return {
        "city": {
            "id": city.city_id,
            "name": city.name,
            "founded_year": city.founded_year,
            "infrastructure": {
                "power_capacity_mw": city.infrastructure.power_capacity_mw,
                "power_output_mw": city.infrastructure.power_output_mw,
                "power_demand_mw": city.infrastructure.power_demand_mw,
                "water_output_m3": city.infrastructure.water_output_m3,
                "road_load": city.infrastructure.road_load,
                "condition": city.infrastructure.condition,
            },
            "weather": {
                "temperature_c": geography.weather.temperature_c,
                "season": geography.weather.season,
                "precipitation_mm": geography.weather.precipitation_mm,
                "wind_kph": geography.weather.wind_kph,
            },
        },
        "region": {
            "name": region.name,
            "population": region.population,
            "climate": region.climate.value,
            "water": region.water,
            "food": region.food,
            "energy": region.energy,
            "pollution": region.pollution,
            "political_stability": region.political_stability,
            "resources": region.resources,
        },
        "districts": [
            {
                "id": d.district_id,
                "name": d.name,
                "kind": d.kind.value,
                "population": d.population,
                "wealth_index": d.wealth_index,
                "pollution": d.pollution,
                "crime_rate": d.crime_rate,
                "unrest": d.unrest,
                "power_reliability": d.power_reliability,
                "transport_load": d.transport_load,
                "buildings": len(d.building_ids),
                "x": d.coordinates.x,
                "y": d.coordinates.y,
            }
            for d in geography.city_districts(city.city_id)
        ],
        "power_plants": [
            {
                "id": p.plant_id,
                "fuel": p.fuel,
                "capacity_mw": p.capacity_mw,
                "output_mw": p.output_mw,
                "availability": p.availability,
                "operator": p.operator_id,
                "district": geography.buildings[p.building_id].district_id if p.building_id in geography.buildings else "",
            }
            for p in sorted(geography.power_plants.values(), key=lambda p: p.plant_id)
        ],
        "housing": {
            "households": len(population.households),
            "homeless_households": population.homelessness,
            "dwelling_capacity": sum(
                b.capacity for b in geography.buildings.values() if b.kind is BuildingKind.HOUSING
            ),
        },
    }


def people_view(state: WorldState, *, limit: int = 50, district: str = "", tier: str = "", query: str = "") -> dict[str, Any]:
    agents = state.domain(AgentsState)
    economy = state.domain(EconomyState)
    people = [p for p in agents.people.values() if p.alive]
    if district:
        people = [p for p in people if p.district_id == district]
    if tier:
        people = [p for p in people if p.tier.value == tier]
    if query:
        needle = query.lower()
        people = [p for p in people if needle in p.name.lower() or needle in p.occupation.lower()]
    people.sort(key=lambda p: (-p.importance, p.person_id))
    return {
        "total": len(people),
        "people": [
            {
                "id": p.person_id,
                "name": p.name,
                "tier": p.tier.value,
                "age": round(p.age_years, 1),
                "district": p.district_id,
                "occupation": p.occupation,
                "employer": p.employer_id,
                "employment": p.employment.value,
                "wealth": money(economy.balance(p.account_id)),
                "energy": p.energy,
                "stress": p.stress,
                "mood": p.mood,
                "political_trust": p.political_trust,
                "activity": p.activity.value,
                "importance": p.importance,
            }
            for p in people[:limit]
        ],
    }


def person_detail(state: WorldState, person_id: str) -> dict[str, Any] | None:
    agents = state.domain(AgentsState)
    person = agents.people.get(person_id)
    if person is None:
        return None
    economy = state.domain(EconomyState)
    knowledge = state.domain(KnowledgeState)
    memory = state.domain(MemoryState)
    social = state.domain(SocialState)
    companies = state.domain(CompaniesState)
    known = knowledge.known(person_id)
    beliefs = knowledge.beliefs.get(person_id, {})
    agent_memory = memory.memories.get(person_id)
    employer = companies.companies.get(person.employer_id)
    return {
        "id": person.person_id,
        "name": person.name,
        "tier": person.tier.value,
        "age": round(person.age_years, 1),
        "sex": person.sex.value,
        "district": person.district_id,
        "household": person.household_id,
        "occupation": person.occupation,
        "employer": {"id": employer.company_id, "name": employer.name} if employer else None,
        "employment": person.employment.value,
        "wage": money(person.wage_minor),
        "wealth": money(economy.balance(person.account_id)),
        "health": person.health,
        "energy": person.energy,
        "stress": person.stress,
        "mood": person.mood,
        "reputation": person.reputation,
        "political_trust": person.political_trust,
        "activity": person.activity.value,
        "wake_tick": person.wake_tick,
        "needs": {
            "food": person.needs.food,
            "rest": person.needs.rest,
            "safety": person.needs.safety,
            "social": person.needs.social,
            "esteem": person.needs.esteem,
            "purpose": person.needs.purpose,
        },
        "personality": {
            "openness": person.personality.openness,
            "conscientiousness": person.personality.conscientiousness,
            "extraversion": person.personality.extraversion,
            "agreeableness": person.personality.agreeableness,
            "neuroticism": person.personality.neuroticism,
            "risk_tolerance": person.personality.risk_tolerance,
            "ambition": person.personality.ambition,
        },
        "goals": [{"label": g.label, "kind": g.kind, "priority": g.priority} for g in person.goals],
        "counts": {
            "known_facts": len(known),
            "beliefs": len(beliefs),
            "relationships": len(social.neighbours(person_id)),
            "memories": (len(agent_memory.episodic) + len(agent_memory.working)) if agent_memory else 0,
        },
        "compute_budget": {
            "llm_calls_per_day": person.compute.llm_calls_per_day,
            "calls_used_today": person.compute.calls_used_today,
            "token_budget": person.compute.token_budget,
            "tokens_used_today": person.compute.tokens_used_today,
        },
        "recent_actions": list(reversed(person.recent_actions)),
        "known_facts": [
            {
                "fact_id": fact_id,
                "topic": knowledge.facts[fact_id].topic if fact_id in knowledge.facts else "unknown",
                "text": knowledge.facts[fact_id].text if fact_id in knowledge.facts else "",
                "value": known_fact.value,
                "confidence": known_fact.confidence,
                "source": known_fact.source.value,
                "distorted": known_fact.distorted,
                "acquired_tick": known_fact.acquired_tick,
            }
            for fact_id, known_fact in sorted(known.items(), key=lambda kv: -kv[1].confidence)[:20]
        ],
        "beliefs": [
            {"topic": b.topic, "position": b.position, "confidence": b.confidence, "updated_tick": b.updated_tick}
            for b in sorted(beliefs.values(), key=lambda b: -b.confidence)[:12]
        ],
        "memories": [
            {"tick": m.tick, "topic": m.topic, "summary": m.summary, "salience": m.salience, "kind": m.kind.value}
            for m in sorted(
                ((agent_memory.working + agent_memory.episodic + agent_memory.summaries) if agent_memory else []),
                key=lambda m: -m.tick,
            )[:15]
        ],
        "relationships": [
            {
                "target": edge.target,
                "name": agents.people[edge.target].name if edge.target in agents.people else edge.target,
                "relation": edge.relation.value,
                "strength": edge.strength,
                "trust": edge.trust,
                "sentiment": edge.sentiment,
                "interactions": edge.interactions,
            }
            for edge in sorted(social.neighbours(person_id), key=lambda e: -e.strength)[:15]
        ],
    }


def companies_view(state: WorldState, *, limit: int = 60, sector: str = "") -> dict[str, Any]:
    companies = state.domain(CompaniesState)
    economy = state.domain(EconomyState)
    firms = companies.active()
    if sector:
        firms = [c for c in firms if c.sector.value == sector]
    firms.sort(key=lambda c: (-c.headcount(), c.company_id))
    return {
        "total": len(firms),
        "bankruptcies": companies.bankruptcies,
        "foundations": companies.foundations,
        "total_employment": companies.total_employment,
        "openings": len(companies.openings),
        "companies": [
            {
                "id": c.company_id,
                "name": c.name,
                "sector": c.sector.value,
                "district": c.district_id,
                "product": c.product_code,
                "headcount": c.headcount(),
                "headcount_target": c.headcount_target,
                "capacity": c.capacity_units,
                "utilisation": c.utilisation,
                "output": c.output_units,
                "price": money(c.price_minor),
                "unit_cost": money(c.unit_cost_minor),
                "margin": round((c.price_minor - c.unit_cost_minor) / max(1, c.price_minor), 4),
                "cash": money(economy.balance(c.account_id)),
                "debt": money(c.debt_minor),
                "strategy": c.strategy.value,
                "months_of_loss": c.months_of_loss,
                "layoffs_total": c.layoffs_total,
                "technology": c.technology,
            }
            for c in firms[:limit]
        ],
    }


def economy_view(state: WorldState) -> dict[str, Any]:
    economy = state.domain(EconomyState)
    companies = state.domain(CompaniesState)
    return {
        "currency": economy.currency_code,
        "cpi": economy.cpi,
        "inflation_annual": economy.inflation_annual,
        "unemployment": economy.unemployment_rate,
        "wage_index": economy.wage_index,
        "policy_rate": economy.policy_rate,
        "money_supply": money(economy.money_supply_minor),
        "imports": money(economy.imports_minor),
        "exports": money(economy.exports_minor),
        "transactions": economy.transactions,
        "markets": [
            {
                "code": code,
                "name": economy.goods[code].name,
                "category": economy.goods[code].category.value,
                "unit": economy.goods[code].unit,
                "price": money(m.price_minor),
                "price_minor": m.price_minor,
                "unit_cost": money(m.unit_cost_minor),
                "supply": round(m.supply, 2),
                "demand": round(m.demand, 2),
                "last_demand": round(m.last_demand, 2),
                "inventory": round(m.inventory, 2),
                "expectation": m.expectation,
                "shortage_ticks": m.shortage_ticks,
                "essential": economy.goods[code].essential,
                "history": m.price_history[-96:],
            }
            for code, m in sorted(economy.markets.items())
        ],
        "banks": [
            {
                "id": b.bank_id,
                "name": b.name,
                "capital": money(b.capital_minor),
                "loans": money(b.loans_minor),
                "npl": money(b.npl_minor),
                "reserve_ratio": b.reserve_ratio,
                "spread": b.spread,
            }
            for b in sorted(economy.banks.values(), key=lambda b: b.bank_id)
        ],
        "loans_outstanding": money(sum(l.outstanding_minor for l in economy.loans.values() if not l.defaulted)),
        "defaults": sum(1 for l in economy.loans.values() if l.defaulted),
        "sectors": _sector_table(companies, economy),
    }


def _sector_table(companies: CompaniesState, economy: EconomyState) -> list[dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for company in companies.active():
        row = table.setdefault(
            company.sector.value,
            {"sector": company.sector.value, "companies": 0, "employment": 0, "output": 0.0, "cash": 0},
        )
        row["companies"] += 1
        row["employment"] += company.headcount()
        row["output"] = round(row["output"] + company.output_units, 2)
        row["cash"] += economy.balance(company.account_id)
    for row in table.values():
        row["cash"] = money(row["cash"])
    return sorted(table.values(), key=lambda r: -r["employment"])


def government_view(state: WorldState) -> dict[str, Any]:
    government = state.domain(GovernmentState)
    economy = state.domain(EconomyState)
    agents = state.domain(AgentsState)
    mayor = agents.people.get(government.mayor_id)
    return {
        "mayor": {"id": mayor.person_id, "name": mayor.name} if mayor else None,
        "ruling_party": government.ruling_party_id,
        "approval": government.approval,
        "approval_history": government.public_support_history[-120:],
        "unrest_index": government.unrest_index,
        "emergency_level": government.emergency_level,
        "protests_active": government.protests_active,
        "treasury": money(economy.balance(government.treasury_account_id)),
        "debt": money(government.debt_minor),
        "revenue_ytd": money(government.revenue_ytd_minor),
        "spending_ytd": money(government.spending_ytd_minor),
        "tax": {
            "income": government.income_tax_rate,
            "vat": government.vat_rate,
            "corporate": government.corporate_tax_rate,
        },
        "welfare_per_day": money(government.welfare_per_day_minor),
        "public_jobs": sum(government.public_jobs.values()),
        "institutions": [
            {
                "id": i.institution_id,
                "name": i.name,
                "kind": i.kind.value,
                "budget": money(i.budget_minor),
                "staff": i.staff,
                "effectiveness": i.effectiveness,
                "integrity": i.integrity,
                "leader": agents.people[i.leader_id].name if i.leader_id in agents.people else "",
            }
            for i in sorted(government.institutions.values(), key=lambda i: i.institution_id)
        ],
        "parties": [
            {
                "id": p.party_id,
                "name": p.name,
                "support": p.support,
                "seats": p.seats,
                "in_power": p.in_power,
                "ideology": p.ideology,
                "leader": agents.people[p.leader_id].name if p.leader_id in agents.people else "",
            }
            for p in sorted(government.parties.values(), key=lambda p: -p.support)
        ],
        "policies": [
            {
                "id": p.policy_id,
                "kind": p.kind.value,
                "label": p.label,
                "value": p.value,
                "target": p.target,
                "enacted_tick": p.enacted_tick,
                "expires_tick": p.expires_tick,
                "cost_per_day": money(p.cost_per_day_minor),
                "rationale": p.rationale,
                "active": p.active,
            }
            for p in sorted(government.policies.values(), key=lambda p: -p.enacted_tick)[:25]
        ],
        "elections": [
            {
                "id": e.election_id,
                "scheduled_tick": e.scheduled_tick,
                "held": e.held,
                "winner": e.winner_party_id,
                "turnout": e.turnout,
                "results": e.results,
            }
            for e in government.elections[-5:]
        ],
        "decision_log": government.decision_log[-20:],
    }


def media_view(state: WorldState) -> dict[str, Any]:
    media = state.domain(MediaState)
    net = state.domain(NetState)
    agents = state.domain(AgentsState)
    return {
        "outlets": [
            {
                "id": o.outlet_id,
                "name": o.name,
                "kind": o.kind.value,
                "business_model": o.business_model.value,
                "bias_government": o.bias_government,
                "bias_business": o.bias_business,
                "sensationalism": o.sensationalism,
                "accuracy": o.accuracy,
                "reputation": o.reputation,
                "audience_share": o.audience_share,
                "reach": o.reach,
                "owners": [agents.people[i].name for i in o.owner_ids if i in agents.people],
            }
            for o in sorted(media.outlets.values(), key=lambda o: -o.audience_share)
        ],
        "publications": [
            {
                "id": p.publication_id,
                "outlet": media.outlets[p.outlet_id].name if p.outlet_id in media.outlets else p.outlet_id,
                "tick": p.tick,
                "topic": p.topic,
                "headline": p.headline,
                "framing": p.framing,
                "sentiment": p.sentiment,
                "reach": p.reach,
                "truth": p.truth.value,
                "fact_id": p.fact_id,
                "event_id": p.event_id,
            }
            for p in media.recent(40)
        ],
        "narratives": [
            {
                "topic": n.topic,
                "dominant": n.dominant,
                "momentum": n.momentum,
                "framings": n.framings,
                "last_tick": n.last_tick,
            }
            for n in sorted(media.narratives.values(), key=lambda n: -n.momentum)[:12]
        ],
        "net": {
            "sites": [
                {"id": s.site_id, "name": s.name, "kind": s.kind.value, "reach": s.reach, "trust": s.trust}
                for s in sorted(net.sites.values(), key=lambda s: -s.reach)
            ],
            "trending": sorted(net.trending.items(), key=lambda kv: -kv[1])[:12],
            "posts": [
                {
                    "id": p.post_id,
                    "site": net.sites[p.site_id].name if p.site_id in net.sites else p.site_id,
                    "author": agents.people[p.author_id].name if p.author_id in agents.people else p.author_id,
                    "tick": p.tick,
                    "topic": p.topic,
                    "text": p.text,
                    "stance": p.stance,
                    "reach": p.reach,
                    "engagement": p.engagement,
                    "truth": p.truth.value,
                }
                for p in sorted(net.posts.values(), key=lambda p: -p.tick)[:30]
            ],
        },
    }


def technology_view(state: WorldState) -> dict[str, Any]:
    technology = state.domain(TechnologyState)
    companies = state.domain(CompaniesState)
    return {
        "tech_level": technology.tech_level,
        "discoveries": technology.discoveries,
        "research_points": technology.research_points_total,
        "nodes": [
            {
                "id": n.tech_id,
                "name": n.name,
                "field": n.field_name.value,
                "difficulty": n.difficulty,
                "progress": n.progress,
                "unlocked": n.unlocked,
                "unlocked_tick": n.unlocked_tick,
                "adoption": n.adoption,
                "prerequisites": n.prerequisites,
                "effects": n.effects,
                "discovered_by": n.discovered_by,
            }
            for n in sorted(technology.nodes.values(), key=lambda n: (not n.unlocked, n.tech_id))
        ],
        "projects": [
            {
                "id": p.project_id,
                "tech": technology.nodes[p.tech_id].name if p.tech_id in technology.nodes else p.tech_id,
                "organisation": companies.companies[p.organisation_id].name
                if p.organisation_id in companies.companies else p.organisation_id,
                "researchers": p.researchers,
                "funding_per_month": money(p.funding_per_month_minor),
                "invested": money(p.invested_minor),
                "active": p.active,
            }
            for p in sorted(technology.projects.values(), key=lambda p: p.project_id)
        ],
    }


def culture_view(state: WorldState) -> dict[str, Any]:
    culture = state.domain(CultureState)
    return {
        "mood_index": culture.mood_index,
        "born_total": culture.born_total,
        "died_total": culture.died_total,
        "slang": culture.slang,
        "trends": [
            {
                "id": t.trend_id,
                "kind": t.kind.value,
                "label": t.label,
                "origin_district": t.origin_district_id,
                "birth_tick": t.birth_tick,
                "popularity": t.popularity,
                "peak": t.peak_popularity,
                "adherents": t.adherents,
                "driver": t.driver_topic,
                "sentiment": t.sentiment,
                "alive": t.dead_tick is None,
            }
            for t in sorted(culture.trends.values(), key=lambda t: -t.popularity)[:30]
        ],
    }


def population_view(state: WorldState) -> dict[str, Any]:
    agents = state.domain(AgentsState)
    population = state.domain(PopulationState)
    return {
        "total": agents.total_population(),
        "individuals": len(agents.people),
        "cohort_population": agents.cohort_population(),
        "births_total": population.births_total,
        "deaths_total": population.deaths_total,
        "average_age": population.average_age,
        "unemployment": population.unemployment_rate,
        "homeless_households": population.homelessness,
        "activity": agents.activity_counts,
        "tiers": {
            "persistent": len(agents.persistent_ids),
            "lightweight": len(agents.lightweight_ids),
            "cohorts": len(agents.cohorts),
            "promotions": agents.promotions,
        },
        "cohorts": [
            {
                "id": c.cohort_id,
                "district": c.district_id,
                "age_band": c.age_band,
                "income_band": c.income_band,
                "size": c.size,
                "employment_rate": c.employment_rate,
                "sentiment": c.sentiment,
                "trust_government": c.trust_government,
                "unrest": c.unrest,
                "news_pressure": c.news_pressure,
                "savings": money(c.savings_minor),
            }
            for c in sorted(agents.cohorts.values(), key=lambda c: -c.size)[:40]
        ],
    }


def chronicle_view(state: WorldState, limit: int = 60) -> dict[str, Any]:
    history = state.domain(HistoryState)
    return {
        "total_events": history.total_events,
        "topic_counts": dict(sorted(history.topic_counts.items(), key=lambda kv: -kv[1])[:25]),
        "chronicle": [
            {
                "event_id": e.event_id,
                "tick": e.tick,
                "sim_time": e.sim_time,
                "topic": e.topic,
                "action": e.action,
                "actor": e.actor,
                "target": e.target,
                "importance": e.importance,
                "summary": e.summary,
                "causes": e.causes,
            }
            for e in sorted(history.chronicle, key=lambda e: -e.tick)[:limit]
        ],
    }
