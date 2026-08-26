"""Media organisations (spec section 17).

Every outlet has owners, a bias, a reputation, an audience and a business model. The same
event therefore produces several narratives, and which one a citizen believes depends on
which outlet they read and how much they trust it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.events.model import TruthStatus
from hydra.kernel.state import DomainState, register_domain


class OutletKind(str, enum.Enum):
    NEWSPAPER = "newspaper"
    BROADCAST = "broadcast"
    NET_NATIVE = "net_native"
    TABLOID = "tabloid"
    INDEPENDENT = "independent"
    STATE = "state"


class BusinessModel(str, enum.Enum):
    ADVERTISING = "advertising"
    SUBSCRIPTION = "subscription"
    STATE_FUNDED = "state_funded"
    OWNER_FUNDED = "owner_funded"
    DONATIONS = "donations"


@dataclass(slots=True)
class Outlet:
    outlet_id: str
    name: str
    kind: OutletKind
    owner_ids: list[str] = field(default_factory=list)
    business_model: BusinessModel = BusinessModel.ADVERTISING
    bias_government: float = 0.0      # -1 hostile .. +1 loyal
    bias_business: float = 0.0
    sensationalism: float = 0.3
    accuracy: float = 0.8
    reputation: float = 0.5
    audience_share: float = 0.1
    reach: int = 0
    revenue_minor: int = 0
    site_id: str = ""
    sources: list[str] = field(default_factory=list)   # person ids feeding them stories


@dataclass(slots=True)
class Publication:
    publication_id: str
    outlet_id: str
    tick: int
    topic: str
    headline: str
    framing: str                      # blame_government | blame_business | reassure | alarm | neutral
    fact_id: str = ""
    sentiment: float = 0.0
    reach: int = 0
    truth: TruthStatus = TruthStatus.TRUE
    event_id: str = ""


@dataclass(slots=True)
class Narrative:
    """Competing interpretations of one topic, with momentum."""

    topic: str
    framings: dict[str, float] = field(default_factory=dict)
    momentum: float = 0.0
    last_tick: int = 0
    dominant: str = ""


@register_domain
@dataclass(slots=True)
class MediaState(DomainState):
    DOMAIN: ClassVar[str] = "media"

    outlets: dict[str, Outlet] = field(default_factory=dict)
    publications: dict[str, Publication] = field(default_factory=dict)
    narratives: dict[str, Narrative] = field(default_factory=dict)
    next_publication_index: int = 0
    max_publications: int = 900

    def new_publication_id(self) -> str:
        self.next_publication_index += 1
        return f"pub_{self.next_publication_index:07d}"

    def add_publication(self, publication: Publication) -> Publication:
        self.publications[publication.publication_id] = publication
        if len(self.publications) > self.max_publications:
            drop = sorted(self.publications, key=lambda k: (self.publications[k].tick, k))
            for key in drop[: len(self.publications) - self.max_publications]:
                del self.publications[key]
        return publication

    def recent(self, limit: int = 20) -> list[Publication]:
        return sorted(self.publications.values(), key=lambda p: (-p.tick, p.publication_id))[:limit]
