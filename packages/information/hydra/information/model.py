"""Subjective knowledge (spec section 9).

The objective world and what people know about it are two different data structures. An agent
never reads ``WorldState``; it reads its own ``KnownFact`` records, which can be missing,
late, distorted or plain false. Every belief carries a source and a confidence, so the
simulation can explain *why* someone acted on something untrue.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, ClassVar

from hydra.events.model import TruthStatus
from hydra.kernel.state import DomainState, register_domain


class Source(str, enum.Enum):
    OBSERVED = "observed"        # saw it personally
    WORK = "work"                # learned at work
    MEDIA = "media"
    SOCIAL = "social"            # heard from someone
    OFFICIAL = "official"        # government/company statement
    RUMOUR = "rumour"
    SEARCH = "search"            # looked it up on HydraNet


@dataclass(slots=True)
class Fact:
    """An objective statement about the world, created by the system that made it true."""

    fact_id: str
    tick: int
    topic: str                       # energy.price | company.layoff | gov.policy ...
    subject: str                     # entity the fact is about
    claim: str                       # machine-readable claim key
    value: float = 0.0
    text: str = ""                   # deterministic rendering, no LLM required
    district_id: str = ""
    importance: float = 0.2
    origin_event_id: str = ""
    truth: TruthStatus = TruthStatus.TRUE
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class KnownFact:
    """One agent's version of a fact. ``value`` may differ from the objective one."""

    fact_id: str
    acquired_tick: int
    source: Source
    confidence: float = 0.6
    value: float = 0.0
    believed_truth: TruthStatus = TruthStatus.UNVERIFIED
    distorted: bool = False
    via: str = ""                    # who or which outlet passed it on
    reinforcements: int = 0


@dataclass(slots=True)
class Belief:
    """A position an agent holds, updated from facts with confidence weighting."""

    topic: str
    position: float = 0.0            # -1 .. +1
    confidence: float = 0.3
    updated_tick: int = 0
    based_on: list[str] = field(default_factory=list)
    contradictions: int = 0


@dataclass(slots=True)
class Observation:
    """One item in an agent's inbox. Sleeping agents accumulate these; waking summarises them."""

    tick: int
    kind: str                        # fact | message | event | delta
    topic: str
    summary: str
    importance: float = 0.2
    fact_id: str = ""
    source: Source = Source.OBSERVED
    via: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@register_domain
@dataclass(slots=True)
class KnowledgeState(DomainState):
    DOMAIN: ClassVar[str] = "information"

    facts: dict[str, Fact] = field(default_factory=dict)
    knowledge: dict[str, dict[str, KnownFact]] = field(default_factory=dict)
    beliefs: dict[str, dict[str, Belief]] = field(default_factory=dict)
    inboxes: dict[str, list[Observation]] = field(default_factory=dict)
    cohort_awareness: dict[str, dict[str, float]] = field(default_factory=dict)
    max_facts: int = 4_000
    max_known_per_agent: int = 400
    max_inbox: int = 60
    spread_events: int = 0
    distortions: int = 0

    # -- objective side -----------------------------------------------------------
    def add_fact(self, fact: Fact) -> Fact:
        self.facts[fact.fact_id] = fact
        if len(self.facts) > self.max_facts:
            for key in sorted(self.facts, key=lambda k: (self.facts[k].tick, k))[: len(self.facts) - self.max_facts]:
                del self.facts[key]
        return fact

    # -- subjective side ----------------------------------------------------------
    def known(self, person_id: str) -> dict[str, KnownFact]:
        return self.knowledge.setdefault(person_id, {})

    def learn(self, person_id: str, known: KnownFact) -> KnownFact:
        store = self.known(person_id)
        existing = store.get(known.fact_id)
        if existing is not None:
            existing.reinforcements += 1
            existing.confidence = min(1.0, existing.confidence + 0.12)
            return existing
        store[known.fact_id] = known
        if len(store) > self.max_known_per_agent:
            for key in sorted(store, key=lambda k: (store[k].confidence, store[k].acquired_tick))[
                : len(store) - self.max_known_per_agent
            ]:
                del store[key]
        return known

    def knows(self, person_id: str, fact_id: str) -> bool:
        return fact_id in self.knowledge.get(person_id, {})

    def belief(self, person_id: str, topic: str) -> Belief:
        person = self.beliefs.setdefault(person_id, {})
        belief = person.get(topic)
        if belief is None:
            belief = Belief(topic=topic)
            person[topic] = belief
        return belief

    # -- inboxes ------------------------------------------------------------------
    def observe(self, person_id: str, observation: Observation) -> None:
        inbox = self.inboxes.setdefault(person_id, [])
        inbox.append(observation)
        if len(inbox) > self.max_inbox:
            inbox.sort(key=lambda o: (-o.importance, -o.tick))
            del inbox[self.max_inbox :]

    def drain_inbox(self, person_id: str) -> list[Observation]:
        inbox = self.inboxes.get(person_id)
        if not inbox:
            return []
        self.inboxes[person_id] = []
        return sorted(inbox, key=lambda o: (o.tick, o.topic))
