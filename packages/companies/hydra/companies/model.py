"""Companies (spec section 14).

A firm is an autonomous unit with cash, staff, inventory, suppliers, customers and a
strategy. It can be founded, hire, fire, invest, produce, compete, merge and go bankrupt —
all as consequences of its own books, never as scripted narrative.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


class Sector(str, enum.Enum):
    ENERGY = "energy"
    WATER = "water"
    AGRICULTURE = "agriculture"
    FOOD = "food"
    MANUFACTURING = "manufacturing"
    ELECTRONICS = "electronics"
    CONSTRUCTION = "construction"
    LOGISTICS = "logistics"
    RETAIL = "retail"
    SERVICES = "services"
    FINANCE = "finance"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    MEDIA = "media"
    TECH = "tech"


class Strategy(str, enum.Enum):
    SURVIVE = "survive"
    COST_CUT = "cost_cut"
    GROW = "grow"
    INVEST = "invest"
    MILK = "milk"


@dataclass(slots=True)
class JobOpening:
    opening_id: str
    company_id: str
    role: str
    wage_minor: int
    skill: str
    skill_required: float
    positions: int
    posted_tick: int
    filled: int = 0


@dataclass(slots=True)
class Company:
    company_id: str
    name: str
    sector: Sector
    district_id: str
    building_id: str
    account_id: str
    product_code: str
    recipe_code: str
    founded_tick: int = 0
    owner_ids: list[str] = field(default_factory=list)
    employee_ids: list[str] = field(default_factory=list)
    cohort_employees: dict[str, int] = field(default_factory=dict)  # cohort_id -> headcount
    headcount_target: int = 0
    average_wage_minor: int = 0
    capacity_units: float = 100.0
    output_units: float = 0.0
    supplied_window: float = 0.0      # units handed to the market since the last clearing
    utilisation: float = 0.85
    inventory: dict[str, float] = field(default_factory=dict)
    input_stock: dict[str, float] = field(default_factory=dict)
    price_minor: int = 0
    unit_cost_minor: int = 0
    revenue_minor: int = 0
    costs_minor: int = 0
    profit_history: list[int] = field(default_factory=list)
    debt_minor: int = 0
    market_share: float = 0.0
    technology: float = 0.5
    productivity: float = 1.0
    strategy: Strategy = Strategy.SURVIVE
    reputation: float = 0.5
    supplier_ids: list[str] = field(default_factory=list)
    customer_ids: list[str] = field(default_factory=list)
    energy_intensity: float = 1.0
    bankrupt: bool = False
    layoffs_total: int = 0
    hires_total: int = 0
    months_of_loss: int = 0
    last_decision: str = ""

    def headcount(self) -> int:
        return len(self.employee_ids) + sum(self.cohort_employees.values())


@register_domain
@dataclass(slots=True)
class CompaniesState(DomainState):
    DOMAIN: ClassVar[str] = "companies"

    companies: dict[str, Company] = field(default_factory=dict)
    openings: dict[str, JobOpening] = field(default_factory=dict)
    next_company_index: int = 0
    next_opening_index: int = 0
    bankruptcies: int = 0
    foundations: int = 0
    total_employment: int = 0
    total_layoffs: int = 0
    total_hires: int = 0

    def active(self) -> list[Company]:
        return [c for c in self.companies.values() if not c.bankrupt]

    def by_sector(self, sector: Sector) -> list[Company]:
        return [c for c in self.active() if c.sector is sector]

    def producers_of(self, code: str) -> list[Company]:
        return [c for c in self.active() if c.product_code == code]
