"""Government and institutions (spec section 15).

Policy is an output, not an input: decisions follow from public support, the economy,
security, ideology, institutional rules and internal politics. A mayor who ignores an
unemployment spike loses support, and losing support changes what the next decision can be.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


class InstitutionKind(str, enum.Enum):
    CITY_GOVERNMENT = "city_government"
    NATIONAL_GOVERNMENT = "national_government"
    PARLIAMENT = "parliament"
    COURT = "court"
    POLICE = "police"
    MILITARY = "military"
    CENTRAL_BANK = "central_bank"
    TAX_AUTHORITY = "tax_authority"
    PUBLIC_SERVICE = "public_service"
    INTELLIGENCE = "intelligence"
    REGULATOR = "regulator"


class PolicyKind(str, enum.Enum):
    ENERGY_SUBSIDY = "energy_subsidy"
    PRICE_CAP = "price_cap"
    TAX_CHANGE = "tax_change"
    WELFARE_BOOST = "welfare_boost"
    PUBLIC_WORKS = "public_works"
    RATIONING = "rationing"
    EMERGENCY_POWERS = "emergency_powers"
    POLICING_SURGE = "policing_surge"
    IMPORT_DEAL = "import_deal"
    AUSTERITY = "austerity"
    RESEARCH_GRANT = "research_grant"


@dataclass(slots=True)
class Institution:
    institution_id: str
    name: str
    kind: InstitutionKind
    account_id: str = ""
    budget_minor: int = 0
    staff: int = 0
    effectiveness: float = 0.7
    integrity: float = 0.7
    leader_id: str = ""
    parent_id: str = ""


@dataclass(slots=True)
class Party:
    party_id: str
    name: str
    ideology: dict[str, float] = field(default_factory=dict)   # market, authority, green, welfare
    support: float = 0.2
    seats: int = 0
    leader_id: str = ""
    in_power: bool = False


@dataclass(slots=True)
class Policy:
    policy_id: str
    kind: PolicyKind
    label: str
    value: float
    enacted_tick: int
    expires_tick: int | None = None
    cost_per_day_minor: int = 0
    proposer_id: str = ""
    support_at_enactment: float = 0.5
    rationale: str = ""
    target: str = ""
    active: bool = True


@dataclass(slots=True)
class Election:
    election_id: str
    scheduled_tick: int
    held: bool = False
    winner_party_id: str = ""
    turnout: float = 0.0
    results: dict[str, float] = field(default_factory=dict)


@register_domain
@dataclass(slots=True)
class GovernmentState(DomainState):
    DOMAIN: ClassVar[str] = "government"

    institutions: dict[str, Institution] = field(default_factory=dict)
    parties: dict[str, Party] = field(default_factory=dict)
    policies: dict[str, Policy] = field(default_factory=dict)
    elections: list[Election] = field(default_factory=list)
    treasury_account_id: str = ""
    city_government_id: str = ""
    ruling_party_id: str = ""
    mayor_id: str = ""
    approval: float = 0.55
    public_support_history: list[float] = field(default_factory=list)
    emergency_level: int = 0
    debt_minor: int = 0
    revenue_ytd_minor: int = 0
    spending_ytd_minor: int = 0
    income_tax_rate: float = 0.17
    vat_rate: float = 0.19
    corporate_tax_rate: float = 0.19
    welfare_per_day_minor: int = 0
    next_policy_index: int = 0
    protests_active: int = 0
    unrest_index: float = 0.05
    last_decision_tick: int = 0
    decision_log: list[str] = field(default_factory=list)
    public_jobs: dict[str, int] = field(default_factory=dict)     # cohort_id -> public headcount
    public_wage_minor: int = 300_000
    procurement_yesterday_minor: int = 0

    def active_policies(self) -> list[Policy]:
        return [p for p in self.policies.values() if p.active]

    def policy_of_kind(self, kind: PolicyKind) -> Policy | None:
        for policy in self.policies.values():
            if policy.active and policy.kind is kind:
                return policy
        return None
