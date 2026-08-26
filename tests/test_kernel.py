"""World kernel: clock, randomness, serialization, scheduling and the action pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from hydra.events.bus import EventBus, InProcessTransport
from hydra.events.importance import ImportanceInputs, ImportanceScorer
from hydra.events.model import Event, Topics
from hydra.kernel.actions import ActionIntent, ActionPipeline, ActionResult
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR, TICKS_PER_YEAR, SimClock
from hydra.kernel.config import WorldConfig
from hydra.kernel.engine import Kernel
from hydra.kernel.errors import ActionRejected, ContractViolation
from hydra.kernel.kernelstate import KernelDomainState
from hydra.kernel.rng import DeterministicRng, derive_seed
from hydra.kernel.serialization import content_hash, decode, encode
from hydra.kernel.state import DomainState, WorldMeta, WorldState, register_domain
from hydra.kernel.systems import Phase, SystemRegistry, SystemSpec


def test_clock_maps_ticks_to_calendar():
    clock = SimClock()
    assert clock.at(0).label() == "Y0-M01-D01 00:00"
    assert clock.at(TICKS_PER_HOUR).hour == 1
    assert clock.at(TICKS_PER_DAY).day == 2
    assert clock.at(TICKS_PER_YEAR).year == 1
    assert clock.at(138).hour == 23


def test_rng_is_reproducible_across_instances():
    a = DeterministicRng(derive_seed(99, "district", "hydra_core"))
    b = DeterministicRng(derive_seed(99, "district", "hydra_core"))
    assert [a.randint(0, 10_000) for _ in range(50)] == [b.randint(0, 10_000) for _ in range(50)]


def test_derived_streams_are_independent():
    parent = DeterministicRng(7)
    first = parent.derive("economy").randint(0, 10**9)
    second = parent.derive("weather").randint(0, 10**9)
    assert first != second
    assert parent.derive("economy").randint(0, 10**9) == first


def test_serialization_round_trips_and_hashes_stably():
    from dataclasses import dataclass, field

    @dataclass(slots=True)
    class Sample:
        name: str
        value: float
        items: list[int] = field(default_factory=list)
        mapping: dict[str, float] = field(default_factory=dict)

    original = Sample(name="hydra", value=1.23456789, items=[3, 1, 2], mapping={"b": 2.0, "a": 1.0})
    payload = encode(original)
    restored = decode(Sample, payload)
    assert restored.items == [3, 1, 2]
    assert restored.mapping == {"b": 2.0, "a": 1.0}
    # Key order must not change the hash; float noise below the precision must not either.
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})
    assert content_hash(Sample("x", 1.0000000001)) == content_hash(Sample("x", 1.0))


def _bare_world() -> tuple[WorldState, WorldConfig]:
    config = WorldConfig()
    state = WorldState(
        meta=WorldMeta(world_id="w", timeline_id="tl_zero", seed=11, config_hash=config.config_hash())
    )
    return state, config


def test_kernel_runs_systems_on_their_cadence():
    state, config = _bare_world()

    class Counter:
        spec = SystemSpec(name="counter", phase=Phase.ENVIRONMENT, cadence_ticks=3, writes=("kernel",))

        def __init__(self) -> None:
            self.runs = 0

        def step(self, ctx) -> None:
            self.runs += 1

    counter = Counter()
    registry = SystemRegistry()
    registry.register(counter)
    Kernel(state, config, registry).run(9)
    assert counter.runs == 3


def test_kernel_isolates_and_quarantines_a_failing_system():
    state, config = _bare_world()

    class Broken:
        spec = SystemSpec(name="broken", phase=Phase.ENVIRONMENT, cadence_ticks=1, writes=("kernel",))

        def step(self, ctx) -> None:
            raise RuntimeError("this system is broken")

    registry = SystemRegistry()
    registry.register(Broken())
    kernel = Kernel(state, config, registry)
    kernel.run(6)

    health = state.domain(KernelDomainState).health["broken"]
    assert health.failures >= config.kernel.quarantine_after_failures
    assert health.quarantined is True
    assert state.meta.tick == 6          # the world kept running


def test_timers_fire_as_events_and_survive_state():
    state, config = _bare_world()
    registry = SystemRegistry()
    kernel = Kernel(state, config, registry)
    kernel.ctx.schedule(3, Topics.KERNEL_SCENARIO, "wake_up", {"reason": "test"})
    seen: list[Event] = []
    kernel.bus.subscribe([Topics.KERNEL_SCENARIO], seen.append, "probe")
    kernel.run(5)
    assert [event.action for event in seen] == ["wake_up"]
    assert seen[0].tick == 3


def test_action_pipeline_validates_before_executing():
    pipeline = ActionPipeline()

    class Handler:
        action = "buy_item"

        def validate(self, ctx, intent):
            if intent.params.get("item") != "food_12":
                raise ActionRejected("unknown_item", str(intent.params.get("item")))
            if intent.params.get("quantity", 0) > 2:
                raise ActionRejected("insufficient_funds", "too many")

        def execute(self, ctx, intent):
            return ActionResult(intent=intent, accepted=True, outcome={"bought": intent.params["quantity"]})

    pipeline.register(Handler())
    ok = pipeline.submit(None, ActionIntent(action="buy_item", actor="person_42",
                                            params={"item": "food_12", "quantity": 2}))
    assert ok.accepted and ok.outcome["bought"] == 2

    rejected = pipeline.submit(None, ActionIntent(action="buy_item", actor="person_42",
                                                  params={"item": "gold", "quantity": 1}))
    assert not rejected.accepted and rejected.reason == "unknown_item"

    unknown = pipeline.submit(None, ActionIntent(action="teleport", actor="person_42"))
    assert not unknown.accepted and unknown.reason == "unknown_action"
    assert pipeline.rejections == 2


def test_event_bus_delivers_only_subscribed_topics():
    bus = EventBus(InProcessTransport())
    market: list[Event] = []
    everything: list[Event] = []
    bus.subscribe(["market.*"], market.append, "markets")
    bus.subscribe(["*"], everything.append, "audit")
    for topic in ("market.price.move", "person.action", "market.shortage"):
        bus.publish(Event(event_id=topic, tick=1, topic=topic, action="x"))
    bus.drain()
    assert len(market) == 2
    assert len(everything) == 3


def test_importance_scores_bounded_and_novelty_decays():
    scorer = ImportanceScorer(population=50_000)
    event = Event(event_id="e", tick=1, topic="company.layoff", action="laid_off_workers")
    first = scorer.score(event, ImportanceInputs(people_affected=500, economic_impact=10_000_000,
                                                 political_impact=0.5, risk=0.4, novelty=1.0))
    repeat = scorer.score(event, ImportanceInputs(people_affected=500, economic_impact=10_000_000,
                                                  political_impact=0.5, risk=0.4, novelty=scorer.novelty(event.topic)))
    assert 0.0 <= repeat <= first <= 1.0


@register_domain
@dataclass(slots=True)
class ProbeState(DomainState):
    """A domain that exists only so a system can be caught writing to it."""

    DOMAIN: ClassVar[str] = "contract_probe"
    counter: int = 0


def test_strict_contracts_catch_an_undeclared_write():
    state, config = _bare_world()
    state.add(ProbeState())

    class Trespasser:
        spec = SystemSpec(name="trespasser", phase=Phase.ENVIRONMENT, cadence_ticks=1, writes=("kernel",))

        def step(self, ctx) -> None:
            ctx.state.domain(ProbeState).counter += 1

    registry = SystemRegistry()
    registry.register(Trespasser())
    kernel = Kernel(state, config, registry, strict_contracts=True)
    kernel.run(1)
    health = state.domain(KernelDomainState).health["trespasser"]
    assert health.failures == 1
    assert "ContractViolation" in health.last_error


def test_no_system_fails_during_a_normal_run():
    """A quarantined system is silent by design; this is what makes it not silent in CI."""

    from hydra.kernel.clock import TICKS_PER_DAY as DAY
    from hydra.world import create_world

    from conftest import small_config

    runtime = create_world(small_config(), seed=606, world_id="world_health")
    runtime.kernel.run(DAY)
    health = runtime.state.domain(KernelDomainState).health
    broken = {name: h.last_error for name, h in health.items() if h.failures}
    assert not broken, f"systems failed during a normal day: {broken}"
