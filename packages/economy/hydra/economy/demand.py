"""Physical demand rates and BOM expansion.

One set of numbers, used in three places: household consumption, cohort consumption and
genesis calibration. That is what keeps the city's capacity, its plants and its shopping
baskets talking about the same world — and what lets a world start in equilibrium instead of
spending its first simulated week finding one.
"""

from __future__ import annotations

from .model import EconomyState

# Per resident, per simulated day, in each good's own unit.
DAILY_PER_RESIDENT: dict[str, float] = {
    "food": 1.0,            # baskets
    "electricity": 9.0,     # kWh (dwelling share)
    "water": 0.15,          # m3
    "transport": 0.35,      # trips
    "consumer_goods": 0.05,
    "services": 0.04,
    "healthcare": 0.010,
    "education": 0.030,
    "electronics": 0.0022,
}

MEAL_HOURS = (7, 12, 18, 19)
COMMUTE_HOURS = (7, 8, 16, 17, 18)
DISCRETIONARY_HEADROOM = 1.15      # room for discretionary buying above the physical baseline


CONTINUOUS = ("electricity", "water")
BATCH = ("consumer_goods", "services", "healthcare", "education", "electronics")
BATCH_HOUR = 18
COMMUTE_TRIPS_PER_WORKER = 2.0


def final_demand_per_day(residents: int, households: int, employed: int) -> dict[str, float]:
    """Demand that exists because people live here, before any industry is considered."""

    demand = {code: rate * residents for code, rate in DAILY_PER_RESIDENT.items()}
    demand["transport"] = DAILY_PER_RESIDENT["transport"] * residents + employed * COMMUTE_TRIPS_PER_WORKER
    demand["housing"] = households / 30.0          # rent is monthly; express it per day
    return demand


def expand_bom(economy: EconomyState, final: dict[str, float], rounds: int = 6) -> dict[str, float]:
    """Add the intermediate demand implied by the bill of materials.

    Producing food needs grain and power; grain needs water and power; power needs fuel. The
    expansion converges quickly because every recipe consumes less than it produces in value.
    """

    total = {code: float(qty) for code, qty in final.items()}
    frontier = dict(total)
    for _ in range(rounds):
        induced: dict[str, float] = {}
        for code, quantity in frontier.items():
            recipe = economy.recipes.get(code)
            if recipe is None or quantity <= 0.0:
                continue
            scale = quantity / max(0.01, recipe.output_qty)
            for input_code, per_unit in recipe.inputs.items():
                induced[input_code] = induced.get(input_code, 0.0) + per_unit * scale
            if recipe.energy_kwh > 0.0:
                induced["electricity"] = induced.get("electricity", 0.0) + recipe.energy_kwh * scale
            if recipe.logistics > 0.0:
                induced["transport"] = induced.get("transport", 0.0) + recipe.logistics * scale
        if not induced:
            break
        for code, quantity in induced.items():
            total[code] = total.get(code, 0.0) + quantity
        frontier = induced
    return {code: round(qty, 3) for code, qty in total.items()}


def estimate_daily_demand(economy: EconomyState, *, residents: int, households: int, employed: int) -> dict[str, float]:
    final = final_demand_per_day(residents, households, employed)
    total = expand_bom(economy, final)
    return {code: round(qty * DISCRETIONARY_HEADROOM, 3) for code, qty in total.items()}


def price_response(economy, code: str, quantity: float) -> float:
    """Scale a wanted quantity by how far the price has moved from its reference.

    Demand that never responds to price is what turns a shortage into hyperinflation: the
    market keeps asking for the same basket at any price, so the price has nowhere to stop.
    """

    market = economy.markets.get(code)
    good = economy.goods.get(code)
    if market is None or good is None or quantity <= 0.0:
        return quantity
    base = economy.cpi_base.get(code) or good.base_price_minor
    if base <= 0:
        return quantity
    ratio = market.price_minor / base
    if ratio <= 1.0:
        return quantity
    return quantity * max(0.15, ratio ** (-good.elasticity))
