"""Households and population accounting.

Households are the unit the housing market, consumption and demography actually operate on;
individuals earn, but households pay rent and buy food.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


@dataclass(slots=True)
class Household:
    household_id: str
    district_id: str
    building_id: str
    member_ids: list[str] = field(default_factory=list)
    cohort_id: str = ""                 # set when the household stands for cohort members
    represented_people: int = 1
    account_id: str = ""
    housing_cost_minor: int = 0
    owns_home: bool = False
    mortgage_minor: int = 0
    savings_minor: int = 0
    monthly_income_minor: int = 0
    monthly_spend_minor: int = 0
    daily_spend_minor: int = 0
    daily_income_minor: int = 0
    food_stock: float = 6.0
    energy_use_kwh: float = 9.0
    children: int = 0
    stress: float = 0.2
    arrears_minor: int = 0
    evicted: bool = False


@register_domain
@dataclass(slots=True)
class PopulationState(DomainState):
    DOMAIN: ClassVar[str] = "population"

    households: dict[str, Household] = field(default_factory=dict)
    next_household_index: int = 0
    total_residents: int = 0
    district_population: dict[str, int] = field(default_factory=dict)
    births_total: int = 0
    deaths_total: int = 0
    immigration_total: int = 0
    emigration_total: int = 0
    unemployment_rate: float = 0.06
    poverty_rate: float = 0.12
    homelessness: int = 0
    average_age: float = 38.0
