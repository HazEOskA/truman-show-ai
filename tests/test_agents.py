"""Agents: subjective knowledge, action validation and the compute ladder."""

from __future__ import annotations

import pytest

from hydra.agents.actions import register_actions
from hydra.agents.brains import UtilityBrain, situation_importance
from hydra.agents.llm.adapter import DisabledAdapter, LLMUnavailable, build_adapter
from hydra.agents.llm.gateway import LLMGateway
from hydra.agents.model import Activity, AgentsState, ComputeBudget, Employment, Tier
from hydra.agents.systems import build_view
from hydra.companies.model import CompaniesState
from hydra.economy.model import EconomyState
from hydra.information.model import KnowledgeState
from hydra.kernel.actions import ActionIntent
from hydra.kernel.clock import TICKS_PER_HOUR
from hydra.kernel.config import LLMConfig
from hydra.kernel.rng import DeterministicRng


def _awake_person(world):
    agents = world.state.domain(AgentsState)
    world.kernel.run(TICKS_PER_HOUR * 10)     # get to a waking hour
    return next(
        p for p in agents.people.values()
        if p.alive and p.activity in (Activity.ACTIVE, Activity.LIGHT_IDLE) and p.age_years > 20
    )


def test_view_contains_only_what_the_agent_knows(world):
    person = _awake_person(world)
    knowledge = world.state.domain(KnowledgeState)
    view = build_view(world.kernel.ctx, person)

    known_ids = set(knowledge.known(person.person_id))
    assert {fact.fact_id for fact in view.known_facts} <= known_ids
    assert len(knowledge.facts) >= len(view.known_facts), "the world knows at least as much as one person"
    assert not hasattr(view, "state"), "the view must not carry a handle on the world"
    payload = view.to_prompt_payload()
    assert set(payload) == {"you", "goals", "knows", "since_last_time", "remembers", "situation"}


def test_posting_a_fact_the_agent_does_not_know_is_rejected(world):
    person = _awake_person(world)
    result = world.kernel.ctx.submit(
        ActionIntent(action="post_online", actor=person.person_id, params={"fact_id": "fact_does_not_exist"})
    )
    assert not result.accepted
    assert result.reason == "unknown_fact"


def test_buying_validates_shop_stock_money_and_location(world):
    person = _awake_person(world)
    economy = world.state.domain(EconomyState)

    unknown = world.kernel.ctx.submit(
        ActionIntent(action="buy_item", actor=person.person_id, params={"item": "unobtainium", "quantity": 1})
    )
    assert unknown.reason == "unknown_item"

    economy.markets["consumer_goods"].inventory = 0.0
    empty = world.kernel.ctx.submit(
        ActionIntent(action="buy_item", actor=person.person_id, params={"item": "consumer_goods", "quantity": 5})
    )
    assert empty.reason == "out_of_stock"

    economy.markets["consumer_goods"].inventory = 1_000.0
    economy.accounts[person.account_id].balance_minor = 0
    economy.accounts[person.account_id].overdraft_minor = 0
    broke = world.kernel.ctx.submit(
        ActionIntent(action="buy_item", actor=person.person_id, params={"item": "consumer_goods", "quantity": 5})
    )
    assert broke.reason == "insufficient_funds"


def test_a_sleeping_agent_cannot_act(world):
    agents = world.state.domain(AgentsState)
    person = next(iter(agents.people.values()))
    person.activity = Activity.SLEEP
    result = world.kernel.ctx.submit(ActionIntent(action="rest", actor=person.person_id))
    assert not result.accepted and result.reason == "actor_asleep"


def test_applying_for_a_filled_opening_is_rejected(world):
    from hydra.economy.systems import post_opening

    companies = world.state.domain(CompaniesState)
    agents = world.state.domain(AgentsState)
    company = companies.active()[0]
    opening = post_opening(
        companies, company, tick=0, role="tester", wage_minor=100_000,
        skill="manual", skill_required=0.1, positions=1,
    )
    opening.filled = 1
    seeker = next(p for p in agents.people.values() if p.employment is Employment.UNEMPLOYED)
    result = world.kernel.ctx.submit(
        ActionIntent(action="apply_for_job", actor=seeker.person_id, params={"opening_id": opening.opening_id})
    )
    assert not result.accepted and result.reason == "opening_filled"


def test_utility_brain_is_deterministic_and_returns_intents_only(world):
    person = _awake_person(world)
    view = build_view(world.kernel.ctx, person)
    brain = UtilityBrain()
    first = brain.decide(view, DeterministicRng(5))
    second = brain.decide(view, DeterministicRng(5))
    assert first is not None
    assert (first.action, first.params) == (second.action, second.params)
    assert 0.0 <= situation_importance(view) <= 1.0


def test_the_world_runs_with_no_llm_provider():
    adapter = build_adapter("disabled")
    assert isinstance(adapter, DisabledAdapter)
    assert adapter.enabled is False
    with pytest.raises(LLMUnavailable):
        adapter.complete(system="s", prompt="p", model="m", max_tokens=10)


def test_gateway_never_calls_without_budget_or_importance():
    gateway = LLMGateway(DisabledAdapter(), LLMConfig(enabled=True))
    assert gateway.enabled is False, "a disabled adapter disables the gateway"

    class YesAdapter(DisabledAdapter):
        enabled = True

    gateway = LLMGateway(YesAdapter(), LLMConfig(enabled=True, escalation_importance=0.6))

    class Person:
        tier = Tier.PERSISTENT
        person_id = "person_1"
        compute = ComputeBudget(llm_calls_per_day=2, token_budget=1_000)

    person = Person()
    assert gateway.may_call(person, importance=0.1, tick=1) == ""       # not important enough
    assert gateway.may_call(person, importance=0.7, tick=1) != ""       # small model
    assert gateway.may_call(person, importance=0.95, tick=1) == LLMConfig().large_model
    person.compute.calls_used_today = 99
    assert gateway.may_call(person, importance=0.95, tick=1) == "", "budget exhausted, stay on rules"


def test_gateway_parses_only_allowed_actions():
    intent = LLMGateway._parse('{"action": "rest", "params": {}, "rationale": "tired"}', "person_1", ["rest"])
    assert intent is not None and intent.action == "rest"
    assert LLMGateway._parse('{"action": "delete_city"}', "person_1", ["rest"]) is None
    assert LLMGateway._parse("not json at all", "person_1", ["rest"]) is None


def test_actions_are_registered_once():
    from hydra.kernel.actions import ActionPipeline

    pipeline = register_actions(ActionPipeline())
    assert "buy_item" in pipeline.known_actions()
    with pytest.raises(ValueError):
        register_actions(pipeline)
