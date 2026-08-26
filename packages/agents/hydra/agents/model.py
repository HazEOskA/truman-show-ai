"""Agent model — the three tiers of spec section 7.

Tier A (persistent individuals), Tier B (lightweight individuals) and Tier C (cohorts) share
one world; only their *resolution* differs. A cohort member who starts mattering historically
is promoted to a persistent individual without the rest of the world noticing a seam.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


class Tier(str, enum.Enum):
    PERSISTENT = "A"       # full agent: memory, goals, may use an LLM
    LIGHTWEIGHT = "B"      # utility AI / FSM, LLM only in exceptional situations
    COHORT = "C"           # statistical, never individually simulated


class Activity(str, enum.Enum):
    ACTIVE = "active"
    LIGHT_IDLE = "light_idle"
    SLEEP = "sleep"
    DORMANT = "dormant"
    OFFSCREEN = "offscreen"


class Employment(str, enum.Enum):
    EMPLOYED = "employed"
    UNEMPLOYED = "unemployed"
    STUDENT = "student"
    RETIRED = "retired"
    CHILD = "child"
    SELF_EMPLOYED = "self_employed"
    PUBLIC = "public"


class Sex(str, enum.Enum):
    F = "f"
    M = "m"


@dataclass(slots=True)
class Personality:
    """OCEAN plus two traits the simulation actually reads."""

    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5
    risk_tolerance: float = 0.5
    ambition: float = 0.5


@dataclass(slots=True)
class Needs:
    food: float = 0.8
    rest: float = 0.8
    safety: float = 0.8
    social: float = 0.6
    esteem: float = 0.5
    purpose: float = 0.5


@dataclass(slots=True)
class Goal:
    goal_id: str
    label: str
    kind: str                    # keep_job | pay_rent | find_work | save | raise_family | gain_power ...
    priority: float = 0.5
    progress: float = 0.0
    deadline_tick: int | None = None
    target: str = ""
    created_tick: int = 0


@dataclass(slots=True)
class ComputeBudget:
    """Spec section 27. Exhausted budget downgrades the brain, it never stalls the world."""

    llm_calls_per_day: int = 0
    calls_used_today: int = 0
    token_budget: int = 0
    tokens_used_today: int = 0
    reasoning_budget: int = 40
    reasoning_used: int = 0
    priority: float = 0.5
    day_of_last_reset: int = -1


@dataclass(slots=True)
class Person:
    person_id: str
    name: str
    tier: Tier
    sex: Sex
    birth_tick: int
    age_years: float
    district_id: str
    household_id: str = ""
    home_building_id: str = ""
    work_building_id: str = ""
    location_building_id: str = ""
    occupation: str = "worker"
    employer_id: str = ""
    employment: Employment = Employment.UNEMPLOYED
    wage_minor: int = 0
    account_id: str = ""
    education: float = 0.5
    skills: dict[str, float] = field(default_factory=dict)
    personality: Personality = field(default_factory=Personality)
    values: dict[str, float] = field(default_factory=dict)
    needs: Needs = field(default_factory=Needs)
    goals: list[Goal] = field(default_factory=list)
    health: float = 0.9
    energy: float = 0.8
    stress: float = 0.2
    mood: float = 0.55
    reputation: float = 0.3
    political_trust: float = 0.5
    consumption_propensity: float = 0.75
    activity: Activity = Activity.ACTIVE
    activity_since_tick: int = 0
    wake_tick: int = 0
    sleep_started_tick: int = -1
    last_active_tick: int = 0
    last_llm_tick: int = -1
    idle_days: float = 0.0
    compute: ComputeBudget = field(default_factory=ComputeBudget)
    last_action: str = ""
    recent_actions: list[str] = field(default_factory=list)
    importance: float = 0.1          # world importance of this person, drives promotion
    alive: bool = True
    death_tick: int | None = None
    promoted_from_cohort: str = ""
    traits: list[str] = field(default_factory=list)

    def is_awake(self) -> bool:
        return self.activity in (Activity.ACTIVE, Activity.LIGHT_IDLE)

    def note_action(self, label: str, limit: int = 12) -> None:
        self.last_action = label
        self.recent_actions.append(label)
        if len(self.recent_actions) > limit:
            del self.recent_actions[: len(self.recent_actions) - limit]


@dataclass(slots=True)
class Cohort:
    """Tier C: thousands of people carried as one statistical record."""

    cohort_id: str
    district_id: str
    age_band: str
    income_band: str
    education_band: str
    size: int
    employment_rate: float = 0.92
    average_income_minor: int = 0
    daily_income_minor: int = 0
    savings_minor: int = 0
    account_id: str = ""
    consumption_propensity: float = 0.8
    health: float = 0.85
    trust_government: float = 0.5
    sentiment: float = 0.55
    unrest: float = 0.05
    awareness: dict[str, float] = field(default_factory=dict)   # fact_id -> share aware 0..1
    migration_pressure: float = 0.0
    news_pressure: float = 0.0        # -1..1, decaying weight of what people have heard
    births_accumulator: float = 0.0
    deaths_accumulator: float = 0.0


@register_domain
@dataclass(slots=True)
class AgentsState(DomainState):
    DOMAIN: ClassVar[str] = "agents"

    people: dict[str, Person] = field(default_factory=dict)
    cohorts: dict[str, Cohort] = field(default_factory=dict)
    persistent_ids: list[str] = field(default_factory=list)
    lightweight_ids: list[str] = field(default_factory=list)
    next_person_index: int = 0
    promotions: int = 0
    deaths: int = 0
    births: int = 0
    activity_counts: dict[str, int] = field(default_factory=dict)

    def alive_people(self) -> list[Person]:
        return [p for p in self.people.values() if p.alive]

    def persistent(self) -> list[Person]:
        return [self.people[i] for i in self.persistent_ids if i in self.people and self.people[i].alive]

    def cohort_population(self) -> int:
        return sum(c.size for c in self.cohorts.values())

    def total_population(self) -> int:
        return sum(1 for p in self.people.values() if p.alive) + self.cohort_population()
