"""AgentView — the only thing a brain is ever given.

Rule 35.9: the global state is never directly available to an agent. The perception system
builds this view out of the agent's own knowledge, memory, inbox and body. If a fact is not
in here, the agent does not know it, and cannot act on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ViewFact:
    fact_id: str
    topic: str
    value: float
    confidence: float
    source: str
    acquired_tick: int
    text: str = ""


@dataclass(slots=True)
class ViewRelation:
    person_id: str
    relation: str
    trust: float
    sentiment: float
    strength: float


@dataclass(slots=True)
class ViewOpening:
    opening_id: str
    company_id: str
    role: str
    wage_minor: int
    skill: str
    skill_required: float


@dataclass(slots=True)
class AgentView:
    person_id: str
    name: str
    tier: str
    tick: int
    hour: int
    age_years: float
    district_id: str
    location_building_id: str
    occupation: str
    employer_id: str
    employed: bool
    wage_minor: int
    balance_minor: int
    energy: float
    stress: float
    mood: float
    health: float
    political_trust: float
    needs: dict[str, float]
    personality: dict[str, float]
    goals: list[str] = field(default_factory=list)
    known_facts: list[ViewFact] = field(default_factory=list)
    beliefs: dict[str, float] = field(default_factory=dict)
    inbox: list[str] = field(default_factory=list)
    inbox_importance: float = 0.0
    memories: list[str] = field(default_factory=list)
    relations: list[ViewRelation] = field(default_factory=list)
    openings: list[ViewOpening] = field(default_factory=list)
    perceived_prices: dict[str, float] = field(default_factory=dict)
    perceived_power_reliability: float = 1.0
    perceived_unrest: float = 0.0
    situation: str = "routine"
    salience: float = 0.0

    def price(self, code: str, default: float = 0.0) -> float:
        return self.perceived_prices.get(code, default)

    def to_prompt_payload(self) -> dict[str, Any]:
        """Compact JSON payload for an LLM. Deliberately small: cost is a design constraint."""

        return {
            "you": {
                "name": self.name,
                "age": round(self.age_years, 1),
                "occupation": self.occupation,
                "employed": self.employed,
                "district": self.district_id,
                "money": round(self.balance_minor / 100.0, 2),
                "energy": self.energy,
                "stress": self.stress,
                "mood": self.mood,
                "political_trust": self.political_trust,
                "needs": self.needs,
            },
            "goals": self.goals[:4],
            "knows": [
                {"topic": f.topic, "value": f.value, "confidence": f.confidence, "source": f.source}
                for f in self.known_facts[:8]
            ],
            "since_last_time": self.inbox[:6],
            "remembers": self.memories[:4],
            "situation": self.situation,
        }
