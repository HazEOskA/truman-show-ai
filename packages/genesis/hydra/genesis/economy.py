"""Genesis of the economy: goods, bills of materials, markets and banks.

The BOM graph is what makes the demo scenario work without a script: electricity is an input
to almost everything, so an energy shock propagates into unit costs, then prices, then
margins, then employment — mechanically.
"""

from __future__ import annotations

from hydra.economy.model import (
    Bank,
    EconomyState,
    Good,
    GoodCategory,
    Market,
    OwnerKind,
    Recipe,
)
from hydra.kernel.config import WorldConfig

from hydra.economy.demand import estimate_daily_demand
from hydra.economy.pricing import equilibrium_prices

from .names import word

INVENTORY_COVER_DAYS = 3.0
WORK_HOURS_PER_DAY = 7.0
HOUSING_INCOME_SHARE = 0.30
BASE_MONTHLY_WAGE_MINOR = 320_000
BASELOAD_COST_MINOR_PER_KWH = 3      # fission variable cost, see PLANT_PLAN
from .seeds import SeedTree

# code, name, category, unit, base price (minor), storable, cpi weight, essential,
# perishable share per day, price elasticity of demand
#
# "Storable" here means the market can hold it between cycles. A bus seat or an hour of a
# plumber's time is storable in that sense for a day — capacity produced in the morning can
# serve the evening peak — but it expires, which is what `perishable_daily` says.
GOODS: tuple[tuple[str, str, GoodCategory, str, int, bool, float, bool, float, float], ...] = (
    ("electricity", "Electricity", GoodCategory.ENERGY, "kWh", 22, False, 0.09, True, 0.0, 0.25),
    ("fuel", "Fuel", GoodCategory.ENERGY, "litre", 140, True, 0.04, False, 0.0, 0.45),
    ("water", "Water", GoodCategory.UTILITY, "m3", 180, False, 0.03, True, 0.0, 0.15),
    ("grain", "Grain", GoodCategory.FOOD, "unit", 40, True, 0.00, False, 0.02, 0.5),
    ("food", "Food basket", GoodCategory.FOOD, "basket", 250, True, 0.16, True, 0.05, 0.3),
    ("materials", "Materials", GoodCategory.MATERIAL, "unit", 320, True, 0.00, False, 0.0, 0.6),
    ("components", "Components", GoodCategory.COMPONENT, "unit", 900, True, 0.00, False, 0.0, 0.7),
    ("electronics", "Electronics", GoodCategory.CONSUMER, "unit", 4500, True, 0.04, False, 0.0, 1.1),
    ("consumer_goods", "Consumer goods", GoodCategory.CONSUMER, "unit", 1200, True, 0.11, False, 0.0, 0.9),
    ("housing", "Housing", GoodCategory.HOUSING, "month", 65_000, False, 0.24, True, 0.0, 0.2),
    ("transport", "Transport", GoodCategory.LOGISTICS, "trip", 200, True, 0.07, True, 0.7, 0.4),
    ("services", "Services", GoodCategory.SERVICE, "hour", 900, True, 0.12, False, 0.7, 1.0),
    ("healthcare", "Healthcare", GoodCategory.SERVICE, "visit", 1500, True, 0.06, True, 0.6, 0.3),
    ("education", "Education", GoodCategory.SERVICE, "month", 1200, True, 0.04, False, 0.6, 0.6),
)

# output -> (output qty, inputs, labour hours, energy kWh, logistics)
RECIPES: dict[str, tuple[float, dict[str, float], float, float, float]] = {
    "electricity": (1.0, {"fuel": 0.09}, 0.0009, 0.0, 0.0),
    "fuel": (1.0, {}, 0.004, 0.35, 0.02),
    "water": (1.0, {}, 0.002, 0.42, 0.0),
    "grain": (1.0, {"water": 0.30}, 0.010, 0.08, 0.02),
    "food": (1.0, {"grain": 0.62, "water": 0.05}, 0.030, 0.22, 0.05),
    "materials": (1.0, {}, 0.045, 1.35, 0.08),
    "components": (1.0, {"materials": 0.55}, 0.070, 1.05, 0.06),
    "electronics": (1.0, {"components": 0.62, "materials": 0.18}, 0.240, 2.60, 0.10),
    "consumer_goods": (1.0, {"materials": 0.30, "components": 0.12}, 0.120, 0.95, 0.09),
    "housing": (1.0, {"materials": 0.04}, 0.400, 4.20, 0.00),
    "transport": (1.0, {"fuel": 0.12}, 0.030, 0.18, 0.00),
    "services": (1.0, {"consumer_goods": 0.02}, 0.850, 0.35, 0.01),
    "healthcare": (1.0, {"consumer_goods": 0.06}, 1.100, 0.90, 0.02),
    "education": (1.0, {"consumer_goods": 0.03}, 1.400, 0.60, 0.01),
}


def build_economy(
    seeds: SeedTree,
    config: WorldConfig,
    total_residents: int,
) -> EconomyState:
    state = EconomyState(currency_code=config.economy.currency_code)
    rng = seeds.rng("economy")
    state.policy_rate = config.economy.interest_rate

    for code, name, category, unit, base_price, storable, weight, essential, perishable, elasticity in GOODS:
        state.goods[code] = Good(
            code=code,
            name=name,
            category=category,
            unit=unit,
            base_price_minor=base_price,
            storable=storable,
            cpi_weight=weight,
            essential=essential,
            perishable_daily=perishable,
            elasticity=elasticity,
        )
        price = int(round(base_price * rng.uniform(0.94, 1.07)))
        state.goods[code].cost_based = code != "housing"
        market = Market(
            code=code,
            price_minor=price,
            previous_price_minor=price,
            inventory=0.0,
            unit_cost_minor=int(price * 0.82),
        )
        market.record_price()
        state.markets[code] = market
        state.cpi_base[code] = price

    for output_code, (qty, inputs, labour, energy, logistics) in RECIPES.items():
        state.recipes[output_code] = Recipe(
            output_code=output_code,
            output_qty=qty,
            inputs=dict(inputs),
            labour_hours=labour,
            energy_kwh=energy,
            logistics=logistics,
        )

    # Central bank first: it is the counterparty for money creation.
    central = state.open_account("central_bank", OwnerKind.CENTRAL_BANK, balance_minor=0)
    state.central_bank_account_id = central.account_id
    external = state.open_account("rest_of_world", OwnerKind.EXTERNAL, balance_minor=0, overdraft_minor=10**15)
    state.external_account_id = external.account_id
    escrow = state.open_account("market_escrow", OwnerKind.EXTERNAL, balance_minor=0)
    state.escrow_account_id = escrow.account_id

    for index in range(3):
        bank_rng = seeds.rng("bank", index)
        bank_id = f"bank_{index + 1:02d}"
        capital = int(bank_rng.uniform(80_000_000, 260_000_000))
        account = state.open_account(bank_id, OwnerKind.BANK, bank_id=bank_id, balance_minor=capital)
        state.banks[bank_id] = Bank(
            bank_id=bank_id,
            name=f"{word(bank_rng, 2)} Bank",
            account_id=account.account_id,
            capital_minor=capital,
            reserve_ratio=round(bank_rng.uniform(0.09, 0.15), 4),
            spread=round(bank_rng.uniform(0.025, 0.05), 4),
            risk_appetite=round(bank_rng.uniform(0.35, 0.75), 4),
        )

    state.cpi = 1.0
    return state


def calibrate_economy(
    state: EconomyState,
    config: WorldConfig,
    *,
    residents: int,
    households: int,
    employed: int,
) -> dict[str, float]:
    """Make the city's books add up before anyone trades in it.

    Three things have to agree at genesis or the world spends its first simulated month
    unwinding an accident: the labour a day of consumption requires must match the labour the
    city can supply, prices must follow from the bills of materials, and rent must be a
    believable share of a wage. All three are derived here, none are hand-tuned constants.
    """

    daily_demand = estimate_daily_demand(state, residents=residents, households=households, employed=employed)

    # 1. Labour intensity: scale every recipe so the city needs roughly the workforce it has.
    required_hours = sum(
        daily_demand.get(code, 0.0) * recipe.labour_hours for code, recipe in state.recipes.items()
    )
    available_hours = max(1.0, employed * WORK_HOURS_PER_DAY)
    if required_hours > 0.0:
        factor = available_hours / required_hours
        for recipe in state.recipes.values():
            recipe.labour_hours = round(recipe.labour_hours * factor, 8)

    # 2. Electricity is priced by the grid, not by a recipe: the world opens at the cost of
    #    the plant carrying the base load, and rises from there whenever a dearer one runs.
    state.markets["electricity"].cost_override_minor = BASELOAD_COST_MINOR_PER_KWH

    # 3. Prices follow costs, including the labour cost we just set.
    equilibrium_prices(state, config.economy.target_margin)

    # 4. Rent is scarcity-priced, so it is pinned to income rather than to a cost.
    workers_per_household = employed / max(1, households)
    monthly_wage = BASE_MONTHLY_WAGE_MINOR
    housing_price = int(HOUSING_INCOME_SHARE * workers_per_household * monthly_wage)
    market = state.markets["housing"]
    market.price_minor = max(1, housing_price)
    market.previous_price_minor = market.price_minor
    market.price_history = [market.price_minor]
    state.cpi_base["housing"] = market.price_minor

    # 5. Opening stock, in days of the demand we just computed.
    for code, market in state.markets.items():
        if state.goods[code].storable:
            market.inventory = round(daily_demand.get(code, 0.0) * INVENTORY_COVER_DAYS, 3)

    state.cpi = 1.0
    state.cpi_history = [1.0]
    return daily_demand


def default_bank(state: EconomyState, rng) -> str:  # noqa: ANN001 - DeterministicRng
    return rng.choice(sorted(state.banks))
