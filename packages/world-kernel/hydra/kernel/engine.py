"""The world kernel.

One tick is: fire timers → run due systems in fixed phase order → deliver events →
persist the important ones → checkpoint. Systems are isolated from each other by failure
handling and (optionally) by contract enforcement.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable

from hydra.events.bus import EventBus
from hydra.events.importance import ImportanceScorer
from hydra.events.model import Event, Visibility

from .actions import ActionPipeline
from .clock import SimClock
from .config import WorldConfig
from .context import EventSink, LLMGateway, TickContext
from .errors import ContractViolation, DeterminismError
from .kernelstate import KernelDomainState
from .scheduler import Scheduler
from .serialization import content_hash, encode
from .snapshots import Snapshot, take_snapshot
from .state import WorldState
from .systems import System, SystemHealth, SystemRegistry
from .telemetry import Telemetry


class Kernel:
    """Owns the world's forward motion. Domains own its meaning."""

    def __init__(
        self,
        state: WorldState,
        config: WorldConfig,
        registry: SystemRegistry,
        *,
        actions: ActionPipeline | None = None,
        bus: EventBus | None = None,
        sink: EventSink | None = None,
        llm: LLMGateway | None = None,
        strict_contracts: bool = False,
        services: dict[str, Any] | None = None,
    ) -> None:
        self.state = state
        self.config = config
        self.registry = registry
        self.clock = SimClock(config.epoch_year)
        self.bus = bus or EventBus()
        self.actions = actions or ActionPipeline()
        self.scheduler = Scheduler(registry)
        self.telemetry = Telemetry()
        self.scorer = ImportanceScorer()
        self.sink = sink
        self.llm = llm
        self.strict_contracts = strict_contracts
        self.snapshot_hook: Callable[[Snapshot], None] | None = None
        self.ctx = TickContext(
            state=state,
            config=config,
            clock=self.clock,
            bus=self.bus,
            telemetry=self.telemetry,
            scorer=self.scorer,
            actions=self.actions,
            scheduler=self.scheduler,
            sink=sink,
            llm=llm,
            services=services,
        )
        if not state.has(KernelDomainState):
            state.add(KernelDomainState())
        # Novelty and action counters live in world state so a replay resumed from a snapshot
        # scores and counts exactly as the original run did.
        kernel_state = state.domain(KernelDomainState)
        self.scorer.bind(kernel_state.topic_seen)
        self._actions_baseline = (self.actions.executions, self.actions.rejections)
        self._wire_subscriptions()

    # -- wiring -------------------------------------------------------------------
    def _wire_subscriptions(self) -> None:
        for system in self.registry.all():
            handler = getattr(system, "on_event", None)
            if handler is None or not system.spec.consumes:
                continue
            self.bus.subscribe(system.spec.consumes, self._wrap_handler(system, handler), system.spec.name)

    def _wrap_handler(self, system: System, handler: Callable[[TickContext, Event], None]):
        def _deliver(event: Event) -> None:
            kstate = self.state.domain(KernelDomainState)
            health = kstate.health.setdefault(system.spec.name, SystemHealth())
            if health.quarantined:
                return
            try:
                with self.ctx.caused_by(event):
                    handler(self.ctx, event)
            except Exception as exc:  # noqa: BLE001 - a broken system must not stop the world
                self._record_failure(system, exc, phase="event")

        return _deliver

    # -- running ------------------------------------------------------------------
    def tick(self) -> int:
        started = time.perf_counter()
        next_tick = self.state.meta.tick + 1
        self.ctx.advance_to(next_tick)
        self.telemetry.reset_counters()
        kstate = self.state.domain(KernelDomainState)

        self._fire_timers(kstate, next_tick)

        delivered: list[Event] = []
        for system in self.scheduler.due_systems(next_tick, kstate):
            self._run_system(system)
            # Drain after every system so consequences cascade inside the same tick, in a
            # fixed order. Handlers may emit further events; the transport keeps draining.
            delivered.extend(self.bus.drain())

        delivered.extend(self.bus.drain())
        self._persist(delivered)

        executed_delta = self.actions.executions - self._actions_baseline[0]
        rejected_delta = self.actions.rejections - self._actions_baseline[1]
        self._actions_baseline = (self.actions.executions, self.actions.rejections)
        kstate.executed_actions += executed_delta
        kstate.rejected_actions += rejected_delta
        self.telemetry.gauge("actions_executed_total", float(kstate.executed_actions))
        self.telemetry.tick_ms = (time.perf_counter() - started) * 1000.0
        # Metrics are published before the checkpoint so a snapshot taken this tick contains
        # this tick's numbers — otherwise a restored world would differ from the live one by
        # exactly one tick of telemetry.
        kstate.metrics = {
            key: round(float(value), 6)
            for key, value in self.telemetry.snapshot(include_wall_clock=False).items()
        }
        self._checkpoint(kstate, next_tick)
        return next_tick

    def run(self, ticks: int, *, on_tick: Callable[[int], None] | None = None) -> int:
        for _ in range(ticks):
            current = self.tick()
            if on_tick is not None:
                on_tick(current)
        return self.state.meta.tick

    def run_until(self, tick: int, **kwargs: Any) -> int:
        remaining = tick - self.state.meta.tick
        if remaining < 0:
            raise DeterminismError("cannot run backwards; restore a snapshot and replay instead")
        return self.run(remaining, **kwargs)

    # -- internals ----------------------------------------------------------------
    def _fire_timers(self, kstate: KernelDomainState, tick: int) -> None:
        for timer in self.scheduler.pop_due_timers(kstate, tick):
            self.ctx.emit(
                timer.topic,
                timer.action,
                actor=timer.actor,
                target=timer.target,
                payload=dict(timer.payload),
                importance=timer.importance,
            )

    def _run_system(self, system: System) -> None:
        before = self._contract_fingerprint(system) if self.strict_contracts else None
        try:
            system.step(self.ctx)
            if before is not None:
                # A contract violation is a system failure like any other: recorded,
                # quarantined after repeats, and never allowed to stop the world.
                self._verify_contract(system, before)
        except Exception as exc:  # noqa: BLE001
            self._record_failure(system, exc, phase="step")
            return
        self.telemetry.incr(f"system.{system.spec.name}.runs")

    def _contract_fingerprint(self, system: System) -> dict[str, str]:
        allowed = set(system.spec.writes)
        return {
            name: content_hash(encode(domain))
            for name, domain in self.state.domains.items()
            if name not in allowed and name != "kernel"
        }

    def _verify_contract(self, system: System, before: dict[str, str]) -> None:
        for name, digest in before.items():
            current = content_hash(encode(self.state.domains[name]))
            if current != digest:
                raise ContractViolation(
                    f"system {system.spec.name!r} wrote domain {name!r} "
                    f"which is not in its declared writes {system.spec.writes}"
                )

    def _record_failure(self, system: System, exc: Exception, *, phase: str) -> None:
        kstate = self.state.domain(KernelDomainState)
        health = kstate.health.setdefault(system.spec.name, SystemHealth())
        health.failures += 1
        health.last_error = f"{type(exc).__name__}: {exc}"
        health.last_failure_tick = self.state.meta.tick
        health.history.append(f"t{self.state.meta.tick} {phase}: {health.last_error}")
        del health.history[:-10]
        if health.failures >= self.config.kernel.quarantine_after_failures:
            health.quarantined = True
        self.telemetry.incr("system_failures")
        self.ctx.emit(
            "kernel.system_failure",
            "system_failed",
            actor=system.spec.name,
            payload={
                "error": health.last_error,
                "phase": phase,
                "failures": health.failures,
                "quarantined": health.quarantined,
            },
            importance=0.35 if not health.quarantined else 0.7,
            visibility=Visibility.HIDDEN,
        )

    def _persist(self, events: Iterable[Event]) -> None:
        if self.sink is None:
            return
        threshold = self.config.kernel.ledger_importance_threshold
        for event in events:
            if event.importance >= threshold:
                self.sink.append(event)

    def _checkpoint(self, kstate: KernelDomainState, tick: int) -> None:
        kcfg = self.config.kernel
        if kcfg.checkpoint_interval > 0 and tick % kcfg.checkpoint_interval == 0:
            kstate.checkpoints[str(tick)] = self.state.state_hash()
            # keep the map bounded; the store holds the full history
            if len(kstate.checkpoints) > 64:
                for key in sorted(kstate.checkpoints, key=int)[:-64]:
                    del kstate.checkpoints[key]
        if kcfg.snapshot_interval > 0 and tick % kcfg.snapshot_interval == 0:
            # Record the snapshot in world state *before* capturing it, so the snapshot knows
            # it exists. A snapshot deliberately emits no event: taking one is a fact about
            # the operator, not about the city, and a replay must not be able to tell whether
            # it is running for the first time.
            kstate.snapshot_ticks.append(tick)
            del kstate.snapshot_ticks[:-256]
            snapshot = take_snapshot(self.state)
            if self.snapshot_hook is not None:
                self.snapshot_hook(snapshot)
            self.telemetry.incr("snapshots_taken")

    # -- helpers ------------------------------------------------------------------
    def state_hash(self) -> str:
        return self.state.state_hash()

    def snapshot(self) -> Snapshot:
        return take_snapshot(self.state)
