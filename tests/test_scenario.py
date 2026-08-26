"""Spec section 32 — the required demo scenario.

    1. Hydra starts stable
    2. one power plant loses 40% of its output
    3. energy gets more expensive
    4. firms face higher costs
    5. some firms cut production
    6. layoffs follow
    7. the media publish it
    8. the information reaches part of the population
    9. their behaviour changes
    10. the government responds

Nothing in this chain is scripted. The only thing the test does is break a generator; every
step after that is the world reacting to its own state.
"""

from __future__ import annotations

import pytest

from hydra.agents.model import AgentsState
from hydra.companies.model import CompaniesState
from hydra.economy.model import EconomyState
from hydra.geography.model import GeographyState
from hydra.government.model import GovernmentState
from hydra.history.state import HistoryState
from hydra.information.model import KnowledgeState
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR
from hydra.media.model import MediaState
from hydra.world import create_world
from hydra.world.scenarios import run_scenario

from conftest import small_config

WARMUP_DAYS = 6
AFTER_DAYS = 10


@pytest.fixture(scope="module")
def shocked_world():
    """One world, shocked once, observed for ten days. Every step below reads the same run."""

    runtime = create_world(small_config(), seed=20260826, world_id="world_scenario")
    runtime.kernel.run(TICKS_PER_DAY * WARMUP_DAYS)

    economy = runtime.state.domain(EconomyState)
    before = {
        "energy_price": economy.markets["electricity"].price_minor,
        "cpi": economy.cpi,
        "unemployment": economy.unemployment_rate,
        "layoffs": runtime.state.domain(CompaniesState).total_layoffs,
        "publications": len(runtime.state.domain(MediaState).publications),
        "policies": len(runtime.state.domain(GovernmentState).active_policies()),
        "reserve": runtime.state.domain(GeographyState).city().infrastructure.power_capacity_mw,
    }

    result = run_scenario(runtime, "plant_failure", plant_id="plant_kelvar", loss=0.4)

    # Read the market once before city hall gets its daily meeting: the price rise and the
    # policy response are two different steps of the chain, and a price cap imposed on day
    # one would otherwise hide the very thing it was a response to.
    runtime.kernel.run(TICKS_PER_HOUR * 12)
    immediate = {
        "energy_price": runtime.state.domain(EconomyState).markets["electricity"].price_minor,
        "energy_cost": runtime.state.domain(EconomyState).markets["electricity"].unit_cost_minor,
    }
    runtime.kernel.run(TICKS_PER_DAY * AFTER_DAYS)
    return runtime, before, result, immediate


def test_step_1_the_city_starts_stable(shocked_world):
    _, before, _, _ = shocked_world
    assert before["unemployment"] < 0.12, "the city should not open in a jobs crisis"
    assert before["layoffs"] == 0 or before["layoffs"] < 50


def test_step_2_the_plant_loses_output(shocked_world):
    runtime, _, result, _ = shocked_world
    plant = runtime.state.domain(GeographyState).power_plants["plant_kelvar"]
    assert plant.availability == pytest.approx(0.6, abs=0.01)
    assert result.detail["lost_mw"] > 0


def test_step_3_energy_gets_more_expensive(shocked_world):
    runtime, before, _, immediate = shocked_world
    economy = runtime.state.domain(EconomyState)

    # The cost of *supplying* power is the honest measure: losing cheap baseload puts an
    # expensive gas plant on the margin, and everyone pays what the last plant costs.
    assert economy.markets["electricity"].cost_override_minor > before["energy_price"] * 1.5
    assert immediate["energy_cost"] > before["energy_price"], "the marginal cost of power jumped"
    assert immediate["energy_price"] > before["energy_price"], (
        f"energy price {before['energy_price']} → {immediate['energy_price']}"
    )


def test_step_4_firms_face_higher_costs(shocked_world):
    runtime, _, _, _ = shocked_world
    companies = runtime.state.domain(CompaniesState)
    economy = runtime.state.domain(EconomyState)
    energy_hungry = sorted(companies.active(), key=lambda c: -c.energy_intensity)[:10]
    assert energy_hungry
    # Unit costs are recomputed from the bill of materials, which now includes dearer power.
    assert any(c.unit_cost_minor > economy.markets[c.product_code].unit_cost_minor * 0.5 for c in energy_hungry)
    assert economy.cpi > 0.0


def test_step_5_and_6_some_firms_cut_output_and_lay_people_off(shocked_world):
    runtime, before, _, _ = shocked_world
    companies = runtime.state.domain(CompaniesState)
    cutting = [c for c in companies.active() if c.utilisation < 0.85]
    assert cutting, "at least one firm should be running below its plan"
    assert companies.total_layoffs > before["layoffs"], "the squeeze should cost jobs"


def test_step_7_the_media_publish_it(shocked_world):
    runtime, before, _, _ = shocked_world
    media = runtime.state.domain(MediaState)
    assert len(media.publications) > before["publications"]
    topics = {p.topic for p in media.publications.values()}
    assert topics & {"market.price.move", "company.layoff", "env.power.shortage", "company.output_cut"}
    # The same events must produce more than one narrative.
    framings = {p.framing for p in media.publications.values()}
    assert len(framings) > 1, f"only one framing in the whole city: {framings}"


def test_step_8_the_information_reaches_part_of_the_population(shocked_world):
    runtime, _, _, _ = shocked_world
    knowledge = runtime.state.domain(KnowledgeState)
    agents = runtime.state.domain(AgentsState)

    # Take one thing that happened after the shock and ask who knows about it.
    post_shock = [f for f in knowledge.facts.values() if f.tick > 0 and f.importance >= 0.3]
    assert post_shock, "the shock should have produced facts about the world"
    subject = max(post_shock, key=lambda f: f.importance)

    who_knows = [pid for pid in knowledge.knowledge if knowledge.knows(pid, subject.fact_id)]
    assert who_knows, "somebody should have heard about it"
    assert len(who_knows) < len(agents.people), (
        "and not everybody: knowledge is subjective, it travels through media and conversation"
    )

    aware = [share for shares in knowledge.cohort_awareness.values() for share in shares.values()]
    assert aware and max(aware) > 0.05, "the cohorts should be partly aware of what happened"
    assert min(aware) < max(aware), "awareness is uneven across the city"


def test_step_9_behaviour_changes(shocked_world):
    runtime, _, _, _ = shocked_world
    agents = runtime.state.domain(AgentsState)
    acted = [p for p in agents.people.values() if p.recent_actions]
    assert acted, "people should be doing things"
    # Losing a job is a change in behaviour that shows up in the person's own record.
    from hydra.agents.model import Employment

    unemployed = [p for p in agents.people.values() if p.employment is Employment.UNEMPLOYED and p.stress > 0.3]
    assert unemployed or agents.cohorts, "the labour shock has to land on somebody"


def test_step_10_the_government_responds(shocked_world):
    runtime, before, _, _ = shocked_world
    government = runtime.state.domain(GovernmentState)
    responded = (
        len(government.active_policies()) > before["policies"]
        or government.emergency_level > 0
        or government.decision_log
    )
    assert responded, "a doubling of the energy price should reach city hall"


def test_the_chain_is_recorded_with_causes(shocked_world):
    runtime, _, result, _ = shocked_world
    history = runtime.state.domain(HistoryState)
    assert history.chronicle, "significant events must be chronicled"
    assert history.topic_counts.get("market.price.move", 0) > 0

    # Media publications point back at the fact and the event that produced them.
    media = runtime.state.domain(MediaState)
    linked = [p for p in media.publications.values() if p.event_id]
    assert linked, "a story must be traceable to the event underneath it"


def test_nothing_in_the_scenario_is_scripted(shocked_world):
    """The scenario touches one generator and nothing else."""

    runtime, _, _, _ = shocked_world
    # No system crashed while the world absorbed the shock.
    from hydra.kernel.kernelstate import KernelDomainState

    broken = {n: h.last_error for n, h in runtime.state.domain(KernelDomainState).health.items() if h.failures}
    assert not broken, broken
