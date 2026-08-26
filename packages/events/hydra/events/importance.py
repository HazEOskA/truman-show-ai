"""World importance score (spec section 28).

The score is the world's attention budget. It decides whether an event wakes agents, whether
an LLM is worth spending, whether the ledger stores the full record or a summary, and whether
media picks the story up. It must therefore be cheap, bounded and explainable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Event

WEIGHTS = {
    "people": 0.30,
    "economic": 0.24,
    "political": 0.18,
    "risk": 0.14,
    "novelty": 0.09,
    "proximity": 0.05,
}


def _log_scale(value: float, full: float) -> float:
    """Map 0..full onto 0..1 with diminishing returns (10 deaths matter, 10 000 do not matter 1000x)."""

    if value <= 0.0:
        return 0.0
    import math

    return min(1.0, math.log1p(value) / math.log1p(full))


@dataclass(slots=True)
class ImportanceInputs:
    people_affected: float = 0.0
    economic_impact: float = 0.0     # in currency minor units
    political_impact: float = 0.0    # 0..1
    risk: float = 0.0                # 0..1, danger to life/stability
    novelty: float = 0.5             # 0..1, 1 = never happened before
    proximity: float = 0.0           # 0..1, closeness to persistent agents


class ImportanceScorer:
    """Stateful because novelty depends on what the world has already seen."""

    __slots__ = ("_seen", "_population", "_gdp_scale")

    def __init__(self, population: int = 50_000, gdp_scale: float = 5_000_000_00) -> None:
        self._seen: dict[str, int] = {}
        self._population = max(1, population)
        self._gdp_scale = max(1.0, gdp_scale)

    def bind(self, seen: dict[str, int]) -> None:
        """Adopt the world's own memory of what has happened before.

        Whether an event is novel is a fact about the world, not about the process running it.
        Keeping the counter in world state is what lets a replay resumed from a snapshot score
        the same event exactly as the original run did.
        """

        self._seen = seen

    def novelty(self, topic: str) -> float:
        count = self._seen.get(topic, 0)
        return 1.0 / (1.0 + 0.35 * count)

    def observe(self, topic: str) -> None:
        self._seen[topic] = self._seen.get(topic, 0) + 1

    def score(self, event: Event, inputs: ImportanceInputs) -> float:
        people = _log_scale(inputs.people_affected, self._population * 0.25)
        economic = _log_scale(abs(inputs.economic_impact), self._gdp_scale * 0.02)
        novelty = inputs.novelty if inputs.novelty is not None else self.novelty(event.topic)
        raw = (
            WEIGHTS["people"] * people
            + WEIGHTS["economic"] * economic
            + WEIGHTS["political"] * min(1.0, max(0.0, inputs.political_impact))
            + WEIGHTS["risk"] * min(1.0, max(0.0, inputs.risk))
            + WEIGHTS["novelty"] * min(1.0, max(0.0, novelty))
            + WEIGHTS["proximity"] * min(1.0, max(0.0, inputs.proximity))
        )
        self.observe(event.topic)
        return round(min(1.0, max(0.0, raw)), 6)
