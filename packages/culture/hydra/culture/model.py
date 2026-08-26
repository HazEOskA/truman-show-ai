"""Culture engine (spec section 18).

Slang, memes, movements and conspiracy theories are generated from what the population is
living through — unemployment, prices, unrest, a blackout — not from a random table. Each
trend keeps a pointer to the conditions that produced it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


class TrendKind(str, enum.Enum):
    SLANG = "slang"
    MEME = "meme"
    MUSIC = "music"
    ART = "art"
    SUBCULTURE = "subculture"
    MOVEMENT = "movement"
    IDEOLOGY = "ideology"
    LEGEND = "legend"
    CONSPIRACY = "conspiracy"
    FASHION = "fashion"


@dataclass(slots=True)
class Trend:
    trend_id: str
    kind: TrendKind
    label: str
    origin_district_id: str
    birth_tick: int
    driver_topic: str = ""
    driver_event_id: str = ""
    popularity: float = 0.05
    momentum: float = 0.02
    sentiment: float = 0.0
    adherents: int = 0
    peak_popularity: float = 0.05
    dead_tick: int | None = None


@register_domain
@dataclass(slots=True)
class CultureState(DomainState):
    DOMAIN: ClassVar[str] = "culture"

    trends: dict[str, Trend] = field(default_factory=dict)
    slang: dict[str, str] = field(default_factory=dict)
    mood_index: float = 0.55
    next_trend_index: int = 0
    born_total: int = 0
    died_total: int = 0

    def alive(self) -> list[Trend]:
        return [t for t in self.trends.values() if t.dead_tick is None]
