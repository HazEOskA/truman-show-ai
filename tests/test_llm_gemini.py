"""Gemini in the loop: a model's answer becomes an action the kernel actually executes.

Two claims are under test, and they are deliberately separate because the project makes them
separately:

1. **A decision from the model reaches the world.** The gateway's JSON goes through the same
   `ActionIntent` → `ctx.submit()` → handler → event path as a rule-based decision. There is
   no privileged route for a model; if it proposes something the world forbids, the kernel
   rejects it like anything else.
2. **The loop consults the model and says so.** Running ticks with a provider configured moves
   `llm_calls` and `tokens_used`, and the ledger fills with events the model's choices caused.

The transport is stubbed — the tests must not need a network, a key, or a bill — but nothing
else is. The gateway, the budget ladder, the parser, the kernel, the handlers and the ledger
are the real ones. What the stub stands in for is the wire, not the logic.

The determinism suite is unaffected on purpose: it runs with no provider, which stays the
supported default. A world with Gemini switched on does not replay to the same state hash,
and this file does not pretend otherwise.
"""

from __future__ import annotations

import json

import pytest

from hydra.agents.brains import UtilityBrain, situation_importance
from hydra.agents.llm.adapter import LLMResponse
from hydra.agents.llm.gateway import LLMGateway
from hydra.agents.model import Activity, AgentsState, Tier
from hydra.agents.systems import build_view
from hydra.kernel.clock import TICKS_PER_HOUR
from hydra.kernel.config import LLMConfig

MODEL = "gemini-3.5-flash"

# Actions whose consequence is public, and therefore whose handlers emit an event. Most of what
# a person does all day -- resting, eating, commuting -- changes their own state and is nobody
# else's news, so the kernel executes it without writing history. To show a model's decision
# arriving in the ledger the test has to have it choose something the city would notice.
#
# `protest` leads because it needs no identifier: an adult in a real district can simply do it.
# The other three take one -- a fact id, an opening id -- which the view now names, so a model
# can reach them too; `test_d` is the case that proves it. This ordering keeps the earlier
# tests focused on the decision path rather than on identifier plumbing.
EMITTING_ACTIONS = ("protest", "post_online", "apply_for_job", "found_company")


class GeminiTransportStub:
    """Stands in for the network hop, and for nothing else.

    It answers in the shape the real `GeminiAdapter` returns — a JSON object, the model id it
    was served by, and a token count — so everything downstream of `complete()` is exercised
    exactly as it would be against the live API. Picking `allowed_actions[0]` out of the prompt
    is what keeps the test honest about the contract: the gateway tells the model what it may
    choose from, and an answer outside that list is thrown away before the kernel sees it.
    """

    name = "gemini"
    enabled = True

    def __init__(self) -> None:
        self.calls = 0
        self.last_system = ""

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int) -> LLMResponse:
        self.calls += 1
        self.last_system = system
        allowed = json.loads(prompt).get("allowed_actions") or []
        if not allowed:
            raise AssertionError("the gateway must tell the model which actions are permitted")
        # Prefer an action the city would notice, the way an agent chasing salience would.
        choice = next((a for a in EMITTING_ACTIONS if a in allowed), allowed[0])
        answer = json.dumps({"action": choice, "params": {}, "rationale": "test decision"})
        return LLMResponse(text=answer, model=model, input_tokens=128, output_tokens=24)


def gemini_gateway(stub: GeminiTransportStub) -> LLMGateway:
    """A real gateway wired to the stub, with the ladder open so the test is not flaky.

    `escalation_importance=0.0` is the one thing tuned for the test: in production the model is
    consulted only when a decision matters enough, and waiting for a sufficiently dramatic hour
    in a four-thousand-person town would make this suite slow and occasionally empty-handed.
    """

    return LLMGateway(
        stub,
        LLMConfig(
            enabled=True,
            provider="gemini",
            small_model=MODEL,
            large_model=MODEL,
            escalation_importance=0.0,
            large_model_importance=2.0,        # never escalate to the large rung here
            daily_calls_per_agent=64,
            max_calls_per_tick=32,
        ),
    )


def _wake_the_city(world):
    """Run to a waking hour. At tick zero it is midnight and nobody is deciding anything."""

    world.run(TICKS_PER_HOUR * 10)


def _awake_persistent_people(world):
    agents = world.state.domain(AgentsState)
    return [
        person
        for person in agents.people.values()
        if person.alive
        and person.tier is Tier.PERSISTENT
        and person.activity in (Activity.ACTIVE, Activity.LIGHT_IDLE)
        and person.age_years > 20
    ]


def _make_the_city_angry(world, person) -> None:
    """Give one agent a reason to act publicly.

    The brain only offers `protest` when grievance clears a threshold -- low trust in the
    government plus visible unrest plus, if it is bad enough, hunger. In a city five hours into
    its first morning nobody is angry yet, so the test creates the conditions the same way a
    scenario would: by moving the world's own numbers, not by loosening the rule.
    """

    from hydra.geography.model import GeographyState

    geography = world.state.domain(GeographyState)
    district = geography.districts[person.district_id]
    district.unrest = 0.6
    person.political_trust = 0.05


def test_a_gemini_decision_is_executed_by_the_kernel(world):
    """Model output -> ActionIntent -> ctx.submit() -> handler -> event in the world."""

    stub = GeminiTransportStub()
    gateway = gemini_gateway(stub)
    ctx = world.kernel.ctx
    _wake_the_city(world)

    candidates = _awake_persistent_people(world)
    assert candidates, "no awake persistent agent to decide for"

    decided = None
    for person in candidates:
        _make_the_city_angry(world, person)
        view = build_view(ctx, person)
        view.salience = situation_importance(view)
        allowed = [option.action for option in UtilityBrain().options(view)]
        if not any(action in EMITTING_ACTIONS for action in allowed):
            continue

        model = gateway.may_call(person, view.salience, ctx.tick)
        assert model == MODEL, "the ladder must route this decision to Gemini"

        intent = gateway.propose(person, view, allowed, model)
        assert intent is not None, "the gateway must turn the model's JSON into an intent"

        # The stamp is the audit trail: this action was proposed by a model, and by which one.
        assert intent.source == f"llm:{MODEL}"
        assert intent.actor == person.person_id
        assert intent.action in allowed

        result = ctx.submit(intent)
        if result.accepted and result.event_id:
            decided = (person, intent, result)
            break

    assert decided is not None, "no model decision reached the kernel and produced an event"
    person, intent, result = decided

    emitted = {event.event_id: event for event in ctx.tick_events()}
    assert result.event_id in emitted, "the event the action produced must exist in the world"
    event = emitted[result.event_id]
    assert event.actor == person.person_id
    assert event.tick == ctx.tick
    # High enough to be written down: the kernel ledgers on importance, not on who asked.
    assert event.importance >= world.config.kernel.ledger_importance_threshold

    assert stub.calls >= 1
    assert gateway.stats.calls == stub.calls
    assert gateway.stats.tokens == stub.calls * 152


def test_b_the_tick_loop_consults_gemini_and_reports_it(world):
    """The agent loop, unmodified, routes decisions through the provider and records the cost."""

    stub = GeminiTransportStub()
    gateway = gemini_gateway(stub)
    ctx = world.kernel.ctx
    _wake_the_city(world)
    ctx.llm = gateway

    before = len(world.ledger.events)

    # `llm_calls` is a counter, and the kernel clears counters at the top of every tick, so it
    # describes one tick rather than the run. Agent brains are on a six-tick cadence, which
    # means most ticks legitimately report zero. Sampling after each tick and keeping the peak
    # is what the number actually means; reading it once at the end would be reading whichever
    # tick happened to finish last.
    peak_calls = 0.0
    peak_tokens = 0.0
    for _ in range(TICKS_PER_HOUR * 6):
        world.run(1)
        sample = ctx.telemetry.snapshot()
        peak_calls = max(peak_calls, sample.get("llm_calls", 0.0))
        peak_tokens = max(peak_tokens, sample.get("tokens_used", 0.0))

    assert stub.calls > 0, "the loop never reached the provider"
    assert peak_calls > 0, "llm_calls must count the decisions the model made"
    assert peak_tokens > 0, "tokens_used must report what those decisions cost"
    assert len(world.ledger.events) > before, "a world whose agents are acting writes history"


def test_c_a_model_answer_the_world_forbids_is_dropped(world):
    """The kernel is the only mutator, so an unpermitted action never becomes an event."""

    class Rogue(GeminiTransportStub):
        def complete(self, *, system: str, prompt: str, model: str, max_tokens: int) -> LLMResponse:
            self.calls += 1
            answer = json.dumps({"action": "delete_city", "params": {}, "rationale": "no"})
            return LLMResponse(text=answer, model=model, input_tokens=10, output_tokens=5)

    stub = Rogue()
    gateway = gemini_gateway(stub)
    ctx = world.kernel.ctx
    _wake_the_city(world)
    candidates = _awake_persistent_people(world)
    assert candidates, "no awake persistent agent to decide for"
    person = candidates[0]
    view = build_view(ctx, person)
    view.salience = situation_importance(view)
    allowed = [option.action for option in UtilityBrain().options(view)]

    assert gateway.propose(person, view, allowed, MODEL) is None
    assert stub.calls == 1, "the call still happened and was still paid for"
    assert gateway.stats.failures == 1


class IdAwareTransport(GeminiTransportStub):
    """A model that does what the identifiers are for: cites one.

    Not cleverness on the stub's part — this is the whole behaviour under test. `post_online`
    and `apply_for_job` are not verbs a model can utter on their own; their handlers read
    `params["fact_id"]` and `params["opening_id"]`, and until the view named them, a model was
    structurally unable to pass validation on either. Reading the id straight back out of the
    prompt is exactly what a real model does with a field spelled the same as the parameter.
    """

    ID_ACTIONS = ("apply_for_job", "post_online")

    def __init__(self) -> None:
        super().__init__()
        self.chose: tuple[str, dict[str, str]] | None = None

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int) -> LLMResponse:
        self.calls += 1
        payload = json.loads(prompt)
        allowed = payload["allowed_actions"]

        if "apply_for_job" in allowed and payload.get("openings"):
            chosen = ("apply_for_job", {"opening_id": payload["openings"][0]["opening_id"]})
        elif "post_online" in allowed and payload.get("knows"):
            chosen = ("post_online", {"fact_id": payload["knows"][0]["fact_id"]})
        else:
            raise AssertionError("the view offered no identifier for any action that needs one")

        self.chose = chosen
        action, params = chosen
        answer = json.dumps({"action": action, "params": params, "rationale": "citing what I know"})
        return LLMResponse(text=answer, model=model, input_tokens=160, output_tokens=28)


def test_d_a_model_can_act_on_an_identifier_the_view_gave_it(world):
    """AgentView -> intent carrying a real object id -> validation -> submit -> event."""

    stub = IdAwareTransport()
    gateway = gemini_gateway(stub)
    ctx = world.kernel.ctx
    _wake_the_city(world)

    decided = None
    for person in _awake_persistent_people(world):
        view = build_view(ctx, person)
        payload = view.to_prompt_payload()

        # The fix itself: the payload names what it shows.
        assert "knows" in payload and "openings" in payload
        assert all("fact_id" in fact for fact in payload["knows"])
        assert all("opening_id" in opening for opening in payload["openings"])
        if not (payload["knows"] or payload["openings"]):
            continue

        view.salience = situation_importance(view)
        allowed = [option.action for option in UtilityBrain().options(view)]
        if not any(action in IdAwareTransport.ID_ACTIONS for action in allowed):
            continue

        intent = gateway.propose(person, view, allowed, MODEL)
        assert intent is not None, "the gateway must turn the model's JSON into an intent"
        assert intent.source == f"llm:{MODEL}"
        assert intent.action in IdAwareTransport.ID_ACTIONS
        assert intent.params, "an action that needs an identifier must carry one"

        result = ctx.submit(intent)
        if result.accepted and result.event_id:
            decided = (person, intent, result, payload)
            break

    assert decided is not None, "no id-bearing action from the model survived validation"
    person, intent, result, payload = decided

    # The id the model used is one this agent was actually shown — not one it invented, and
    # not one belonging to somebody else. Subjective knowledge survives the round trip.
    if intent.action == "post_online":
        assert intent.params["fact_id"] in {fact["fact_id"] for fact in payload["knows"]}
    else:
        assert intent.params["opening_id"] in {o["opening_id"] for o in payload["openings"]}

    event = next(event for event in ctx.tick_events() if event.event_id == result.event_id)
    assert event.actor == person.person_id
    assert event.tick == ctx.tick


def test_e_an_invented_identifier_is_still_refused(world):
    """The fix hands the model real ids; it must not become a way to smuggle in a fake one."""

    class Forger(GeminiTransportStub):
        def complete(self, *, system: str, prompt: str, model: str, max_tokens: int) -> LLMResponse:
            self.calls += 1
            answer = json.dumps(
                {"action": "post_online", "params": {"fact_id": "fact_i_made_this_up"}, "rationale": "no"}
            )
            return LLMResponse(text=answer, model=model, input_tokens=40, output_tokens=12)

    stub = Forger()
    gateway = gemini_gateway(stub)
    ctx = world.kernel.ctx
    _wake_the_city(world)

    person = next(
        p for p in _awake_persistent_people(world)
        if "post_online" in [o.action for o in UtilityBrain().options(build_view(ctx, p))]
    )
    view = build_view(ctx, person)
    view.salience = situation_importance(view)
    allowed = [option.action for option in UtilityBrain().options(view)]

    intent = gateway.propose(person, view, allowed, MODEL)
    assert intent is not None, "the verb is permitted, so the gateway hands it on"

    result = ctx.submit(intent)
    assert not result.accepted, "a fact the agent does not know must not become a post"
    assert result.reason == "unknown_fact"
