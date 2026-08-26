"""TickContext — everything a system is allowed to touch during a tick.

A system never reaches for globals: state, randomness, clock, bus, actions and budgets all
arrive through this object. That is what makes systems testable in isolation and what keeps
determinism auditable (every random draw comes from a labelled, derived stream).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Protocol

from hydra.events.importance import ImportanceInputs, ImportanceScorer
from hydra.events.model import Event, TruthStatus, Visibility

from .actions import ActionIntent, ActionPipeline, ActionResult
from .clock import SimClock, SimTime
from .config import WorldConfig
from .ids import event_id as make_event_id
from .kernelstate import KernelDomainState
from .rng import DeterministicRng
from .scheduler import Scheduler
from .state import WorldState
from .telemetry import Telemetry


class EventSink(Protocol):
    """Where ledgered events go. Implemented by the history package."""

    def append(self, event: Event) -> None: ...


class LLMGateway(Protocol):
    """Optional. The world must run to completion when this is absent."""

    enabled: bool

    def propose(self, ctx, agent_view, options) -> ActionIntent | None: ...  # noqa: ANN001


class TickContext:
    __slots__ = (
        "state", "config", "clock", "now", "bus", "telemetry", "scorer", "actions",
        "scheduler", "llm", "sink", "_rng", "_cause_stack", "_tick_events", "services",
    )

    def __init__(
        self,
        *,
        state: WorldState,
        config: WorldConfig,
        clock: SimClock,
        bus,
        telemetry: Telemetry,
        scorer: ImportanceScorer,
        actions: ActionPipeline,
        scheduler: Scheduler,
        sink: EventSink | None = None,
        llm: LLMGateway | None = None,
        services: dict[str, Any] | None = None,
    ) -> None:
        self.state = state
        self.config = config
        self.clock = clock
        self.now: SimTime = clock.at(state.meta.tick)
        self.bus = bus
        self.telemetry = telemetry
        self.scorer = scorer
        self.actions = actions
        self.scheduler = scheduler
        self.sink = sink
        self.llm = llm
        self.services = services if services is not None else {}
        self._rng = DeterministicRng(state.meta.seed)
        self._cause_stack: list[str] = []
        self._tick_events: list[Event] = []

    # -- lifecycle ----------------------------------------------------------------
    def advance_to(self, tick: int) -> None:
        self.state.meta.tick = tick
        self.now = self.clock.at(tick)
        self._tick_events = []

    @property
    def tick(self) -> int:
        return self.state.meta.tick

    @property
    def kernel_state(self) -> KernelDomainState:
        return self.state.domain(KernelDomainState)

    # -- randomness ---------------------------------------------------------------
    def rng(self, *labels: object) -> DeterministicRng:
        """A stream unique to (world seed, tick, labels).

        Two systems drawing numbers in the same tick never interfere, so adding a system
        cannot change another system's random sequence.
        """

        return DeterministicRng(
            _derive(self.state.meta.seed, self.state.meta.timeline_id, self.tick, *labels)
        )

    def stable_rng(self, *labels: object) -> DeterministicRng:
        """Tick-independent stream — for properties that must never change over time."""

        return DeterministicRng(_derive(self.state.meta.seed, *labels))

    # -- causality ----------------------------------------------------------------
    @contextmanager
    def caused_by(self, event: Event | str | None) -> Iterator[None]:
        eid = event.event_id if isinstance(event, Event) else event
        if eid:
            self._cause_stack.append(eid)
        try:
            yield
        finally:
            if eid:
                self._cause_stack.pop()

    # -- events -------------------------------------------------------------------
    def emit(
        self,
        topic: str,
        action: str,
        *,
        actor: str | None = None,
        target: str | None = None,
        location: str | None = None,
        payload: dict[str, Any] | None = None,
        importance: float | None = None,
        inputs: ImportanceInputs | None = None,
        visibility: Visibility = Visibility.PUBLIC,
        truth: TruthStatus = TruthStatus.TRUE,
        causes: list[str] | None = None,
    ) -> Event:
        event = Event(
            event_id=make_event_id(self.state.next_event_seq()),
            tick=self.tick,
            topic=topic,
            action=action,
            actor=actor,
            target=target,
            location=location,
            payload=payload or {},
            causes=list(causes or []) + list(self._cause_stack),
            visibility=visibility,
            truth=truth,
            sim_time=self.now.label(),
            timeline_id=self.state.meta.timeline_id,
        )
        if importance is not None:
            event.importance = round(min(1.0, max(0.0, importance)), 6)
            self.scorer.observe(topic)
        else:
            scoring = inputs or ImportanceInputs(novelty=self.scorer.novelty(topic))
            if inputs is not None and inputs.novelty == 0.5:
                scoring.novelty = self.scorer.novelty(topic)
            event.importance = self.scorer.score(event, scoring)
        self.bus.publish(event)
        self._tick_events.append(event)
        self.telemetry.incr("events_emitted")
        return event

    def tick_events(self) -> list[Event]:
        return list(self._tick_events)

    # -- actions ------------------------------------------------------------------
    def submit(self, intent: ActionIntent) -> ActionResult:
        result = self.actions.submit(self, intent)
        if result.accepted:
            self.telemetry.incr("actions_executed")
        else:
            self.telemetry.incr("actions_rejected")
            self.emit(
                "kernel.action_rejected",
                "action_rejected",
                actor=intent.actor,
                payload={"action": intent.action, "reason": result.reason, "detail": result.detail},
                importance=0.02,
                visibility=Visibility.HIDDEN,
            )
        return result

    # -- timers -------------------------------------------------------------------
    def schedule(
        self,
        fire_tick: int,
        topic: str,
        action: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.scheduler.schedule_at(self.kernel_state, fire_tick, topic, action, payload, **kwargs)


def _derive(seed: int, *labels: object) -> int:
    from .rng import derive_seed

    return derive_seed(seed, *labels)
