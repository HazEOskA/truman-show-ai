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
        """Compact JSON payload for an LLM. Deliberately small: cost is a design constraint.

        The identifiers are here for a reason that took a failing end-to-end run to notice.
        Several actions the world offers are not verbs on their own -- posting requires *which*
        fact, applying requires *which* opening -- and their handlers read `params["fact_id"]`
        and `params["opening_id"]`. A payload that described facts by topic and value but never
        named them left a model able to choose `post_online` and structurally unable to pass
        validation: every attempt came back `unknown_fact`. The rule doing the rejecting is
        correct and stays exactly as it was; what was missing is that the view never told the
        agent which of its own facts it was allowed to cite.

        The keys are deliberately spelled the way the handlers read them. A model copying
        `fact_id` out of `knows` into `params` is then doing the obvious thing rather than
        guessing at a parameter name, and none of that guidance has to live in the prompt.

        Nothing here widens what an agent knows. Every fact in `knows` is already in this
        agent's own knowledge, and every opening in `openings` was already filtered by the
        perception system to this agent's district and to positions still unfilled.
        """

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
                {
                    "fact_id": f.fact_id,
                    "topic": f.topic,
                    "value": f.value,
                    "confidence": f.confidence,
                    "source": f.source,
                }
                for f in self.known_facts[:8]
            ],
            # Only for someone who could actually take the job: `apply_for_job` rejects an
            # already-employed applicant, so sending an employed agent a list of vacancies is
            # tokens spent on an action the world would refuse anyway.
            "openings": [
                {
                    "opening_id": o.opening_id,
                    "role": o.role,
                    "wage": round(o.wage_minor / 100.0, 2),
                    "skill": o.skill,
                    "skill_required": o.skill_required,
                }
                for o in (self.openings[:5] if not self.employed else [])
            ],
            "since_last_time": self.inbox[:6],
            "remembers": self.memories[:4],
            "situation": self.situation,
        }
