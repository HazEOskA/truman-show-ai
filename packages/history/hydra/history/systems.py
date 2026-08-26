"""History system: keeps the in-world chronicle in sync with the event stream."""

from __future__ import annotations

from hydra.events.model import Event
from hydra.kernel.systems import Phase, SystemSpec

from .state import ChronicleEntry, HistoryState

CHRONICLE_THRESHOLD = 0.35


class HistorySystem:
    spec = SystemSpec(
        name="history",
        phase=Phase.INFORMATION,
        cadence_ticks=0,                    # purely event-driven
        priority=900,
        writes=("history",),
        consumes=("*",),
        description="Indexes significant events into the in-world chronicle and topic counters.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001 - event driven only
        return

    def on_event(self, ctx, event: Event) -> None:  # noqa: ANN001
        state = ctx.state.domain(HistoryState)
        state.total_events += 1
        state.topic_counts[event.topic] = state.topic_counts.get(event.topic, 0) + 1
        if event.importance < CHRONICLE_THRESHOLD:
            return
        state.chronicle.append(
            ChronicleEntry(
                event_id=event.event_id,
                tick=event.tick,
                sim_time=event.sim_time,
                topic=event.topic,
                action=event.action,
                actor=event.actor,
                target=event.target,
                importance=event.importance,
                summary=event.headline(),
                causes=list(event.causes),
            )
        )
        if len(state.chronicle) > state.max_chronicle:
            del state.chronicle[: len(state.chronicle) - state.max_chronicle]
