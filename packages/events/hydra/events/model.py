"""Event schema (spec section 21).

Every significant mutation in the world produces exactly one event, and every event carries
causal metadata. The ledger, the causal graph, media pickup, agent wake-ups and LLM
escalation all read from this one structure.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Visibility(str, enum.Enum):
    """Who *can* learn about this event. Not who did — that is the information system's job."""

    PRIVATE = "private"        # only the actor
    LOCAL = "local"            # people co-located, neighbours, colleagues
    ORGANISATIONAL = "org"     # members of a company/institution
    PUBLIC = "public"          # observable by anyone in the city
    HIDDEN = "hidden"          # happened, but nobody observed it (crime, back-room deal)


class TruthStatus(str, enum.Enum):
    TRUE = "true"
    DISTORTED = "distorted"
    FALSE = "false"
    UNVERIFIED = "unverified"


class Topics:
    """Canonical topic names. Systems subscribe to a topic or a prefix."""

    # world / physical
    ENV_WEATHER = "env.weather"
    ENV_POWER_OUTPUT = "env.power.output"
    ENV_POWER_SHORTAGE = "env.power.shortage"
    ENV_WATER = "env.water"
    ENV_INCIDENT = "env.incident"
    TRANSPORT_CONGESTION = "transport.congestion"

    # economy
    MARKET_PRICE_MOVE = "market.price.move"
    MARKET_SHORTAGE = "market.shortage"
    ECON_PRODUCTION = "econ.production"
    ECON_TRADE = "econ.trade"
    ECON_INFLATION = "econ.inflation"
    BANK_LOAN = "bank.loan"
    BANK_DEFAULT = "bank.default"

    # companies
    COMPANY_FOUNDED = "company.founded"
    COMPANY_HIRE = "company.hire"
    COMPANY_LAYOFF = "company.layoff"
    COMPANY_PRICE = "company.price"
    COMPANY_OUTPUT_CUT = "company.output_cut"
    COMPANY_INVEST = "company.invest"
    COMPANY_BANKRUPT = "company.bankrupt"

    # people
    PERSON_ACTION = "person.action"
    PERSON_SLEEP = "person.sleep"
    PERSON_WAKE = "person.wake"
    PERSON_JOB_LOST = "person.job_lost"
    PERSON_HIRED = "person.hired"
    PERSON_MOVED = "person.moved"
    PERSON_BIRTH = "person.birth"
    PERSON_DEATH = "person.death"
    PERSON_RELATIONSHIP = "person.relationship"
    PERSON_PROTEST = "person.protest"
    PERSON_PROMOTED_TIER = "person.promoted_tier"

    # institutions
    GOV_POLICY = "gov.policy"
    GOV_BUDGET = "gov.budget"
    GOV_ELECTION = "gov.election"
    GOV_EMERGENCY = "gov.emergency"

    # information
    MEDIA_PUBLISH = "media.publish"
    NET_POST = "net.post"
    INFO_SPREAD = "info.spread"
    INFO_RUMOUR = "info.rumour"

    # knowledge & culture
    TECH_DISCOVERY = "tech.discovery"
    TECH_ADOPTION = "tech.adoption"
    CULTURE_TREND = "culture.trend"

    # kernel
    KERNEL_SYSTEM_FAILURE = "kernel.system_failure"
    KERNEL_ACTION_REJECTED = "kernel.action_rejected"
    KERNEL_SNAPSHOT = "kernel.snapshot"
    KERNEL_SCENARIO = "kernel.scenario"
    KERNEL_TIMELINE_FORK = "kernel.timeline_fork"


@dataclass(slots=True)
class Event:
    event_id: str
    tick: int
    topic: str
    action: str
    actor: str | None = None
    target: str | None = None
    location: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    causes: list[str] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)
    importance: float = 0.0
    visibility: Visibility = Visibility.PUBLIC
    truth: TruthStatus = TruthStatus.TRUE
    sim_time: str = ""
    timeline_id: str = ""

    def headline(self) -> str:
        """Short, language-free description. Media systems turn this into prose."""

        bits = [self.action.replace("_", " ")]
        if self.target:
            bits.append(f"→ {self.target}")
        return " ".join(bits)
