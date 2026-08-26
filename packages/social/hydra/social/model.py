"""Temporal social graph (spec section 11).

Edges carry strength, trust, sentiment and their own history, because who trusted whom
*at the time* is what explains later behaviour. Stored as a relational-style adjacency map:
Postgres-friendly, no graph database needed for the MVP.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


class Relation(str, enum.Enum):
    FRIEND = "friend"
    FAMILY = "family"
    PARTNER = "partner"
    ENEMY = "enemy"
    TRUSTS = "trusts"
    WORKS_FOR = "works_for"
    OWNS = "owns"
    SUPPORTS = "supports"
    VOTES_FOR = "votes_for"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    ALLY = "ally"
    COMPETITOR = "competitor"
    NEIGHBOUR = "neighbour"
    COLLEAGUE = "colleague"


@dataclass(slots=True)
class EdgeChange:
    tick: int
    field_name: str
    old_value: float
    new_value: float
    reason: str = ""


@dataclass(slots=True)
class Relationship:
    edge_id: str
    source: str
    target: str
    relation: Relation
    strength: float = 0.4
    trust: float = 0.5
    sentiment: float = 0.1
    since_tick: int = 0
    last_interaction_tick: int = 0
    interactions: int = 0
    history: list[EdgeChange] = field(default_factory=list)
    active: bool = True

    def adjust(self, tick: int, *, field_name: str, delta: float, reason: str = "") -> None:
        old = getattr(self, field_name)
        new = round(min(1.0, max(-1.0 if field_name == "sentiment" else 0.0, old + delta)), 6)
        setattr(self, field_name, new)
        if abs(new - old) >= 0.05:
            self.history.append(
                EdgeChange(tick=tick, field_name=field_name, old_value=old, new_value=new, reason=reason)
            )
            del self.history[:-12]


@register_domain
@dataclass(slots=True)
class SocialState(DomainState):
    DOMAIN: ClassVar[str] = "social"

    edges: dict[str, Relationship] = field(default_factory=dict)
    by_source: dict[str, list[str]] = field(default_factory=dict)
    by_target: dict[str, list[str]] = field(default_factory=dict)
    edge_count: int = 0

    @staticmethod
    def edge_key(source: str, target: str, relation: Relation) -> str:
        return f"{source}|{relation.value}|{target}"

    def link(
        self,
        source: str,
        target: str,
        relation: Relation,
        *,
        tick: int,
        strength: float = 0.4,
        trust: float = 0.5,
        sentiment: float = 0.1,
    ) -> Relationship:
        key = self.edge_key(source, target, relation)
        edge = self.edges.get(key)
        if edge is None:
            edge = Relationship(
                edge_id=key,
                source=source,
                target=target,
                relation=relation,
                strength=strength,
                trust=trust,
                sentiment=sentiment,
                since_tick=tick,
                last_interaction_tick=tick,
            )
            self.edges[key] = edge
            self.by_source.setdefault(source, []).append(key)
            self.by_target.setdefault(target, []).append(key)
            self.edge_count += 1
        return edge

    def neighbours(self, person_id: str, relation: Relation | None = None) -> list[Relationship]:
        keys = self.by_source.get(person_id, [])
        edges = [self.edges[k] for k in keys if k in self.edges]
        if relation is not None:
            edges = [e for e in edges if e.relation is relation]
        return [e for e in edges if e.active]

    def inbound(self, person_id: str, relation: Relation | None = None) -> list[Relationship]:
        keys = self.by_target.get(person_id, [])
        edges = [self.edges[k] for k in keys if k in self.edges]
        if relation is not None:
            edges = [e for e in edges if e.relation is relation]
        return [e for e in edges if e.active]

    def between(self, a: str, b: str) -> list[Relationship]:
        return [e for e in self.neighbours(a) if e.target == b]
