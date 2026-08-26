"""Price formation.

Prices are an output of the world, never an input written by a model. A unit cost is built
from the bill of materials — inputs, energy, labour, logistics — and the market price moves
from that floor according to imbalance, inventory and expectations.
"""

from __future__ import annotations

from .model import EconomyState

WORK_HOURS_PER_MONTH = 210.0     # 7 hours × 30 days


def hourly_wage_minor(state: EconomyState, base_monthly_minor: int = 320_000) -> int:
    return int(base_monthly_minor * state.wage_index / WORK_HOURS_PER_MONTH)


def unit_cost_minor(state: EconomyState, code: str) -> int:
    """Cost of producing one unit at current input prices."""

    market = state.markets.get(code)
    if market is not None and market.cost_override_minor > 0:
        # A physical system knows better than the recipe: electricity costs what the last
        # generator dispatched costs, not what an average kWh costs.
        return market.cost_override_minor
    recipe = state.recipes.get(code)
    if recipe is None:
        return state.markets[code].unit_cost_minor
    cost = 0.0
    for input_code, qty in recipe.inputs.items():
        market = state.markets.get(input_code)
        if market is not None:
            cost += market.price_minor * qty
    electricity = state.markets.get("electricity")
    if electricity is not None:
        cost += electricity.price_minor * recipe.energy_kwh
    transport = state.markets.get("transport")
    if transport is not None and code != "transport":
        cost += transport.price_minor * recipe.logistics
    cost += hourly_wage_minor(state) * recipe.labour_hours
    return max(1, int(round(cost / max(0.01, recipe.output_qty))))


TARGET_COVER_DAYS = 3.0


def next_price_minor(
    state: EconomyState,
    code: str,
    *,
    target_margin: float,
    change_cap: float,
    drift: float,
    cycles_per_day: float = 24.0,
) -> int:
    """One price step for one good."""

    market = state.markets[code]
    good = state.goods[code]

    if market.supply <= 0.0 and market.demand <= 0.0:
        # No trade this cycle. A market with nothing happening in it has no new information,
        # and letting expectations drift on an empty market is how prices spiral for no reason.
        return market.price_minor

    supply = max(market.supply, 1e-6)
    imbalance = max(-1.0, min(3.0, (market.demand - market.supply) / supply))

    inventory_pressure = 0.0
    if good.storable:
        daily_demand = max(market.demand * cycles_per_day, 1e-6)
        cover_days = market.inventory / daily_demand
        inventory_pressure = max(-0.25, min(0.25, (TARGET_COVER_DAYS - cover_days) * 0.02))

    expectation = max(-1.0, min(1.0, market.expectation))
    move = drift * imbalance * 0.5 + inventory_pressure + 0.03 * expectation
    move = max(-change_cap, min(change_cap, move))

    # Below a certain price a percentage cap rounds to nothing, and a cheap good would be
    # frozen forever at whatever it opened at. Always allow one minor unit of movement.
    step = max(1.0, market.price_minor * change_cap)

    price = market.price_minor * (1.0 + move)
    if good.cost_based:
        cost_floor = market.unit_cost_minor * (1.0 + target_margin * 0.45)
        if price < cost_floor:
            # Producers do not sell below cost for long; the floor rises with input costs.
            price = min(cost_floor, market.price_minor + step)
    ceiling = market.price_minor + step
    floor = market.price_minor - step
    return max(1, int(round(max(min(price, ceiling), floor))))


def equilibrium_prices(state: EconomyState, target_margin: float, rounds: int = 24) -> None:
    """Fixed-point pass so a new world starts at cost-consistent prices.

    Without it the first simulated week is just the economy discovering that its opening
    prices had nothing to do with its bills of materials.
    """

    for _ in range(rounds):
        for code in sorted(state.markets):
            good = state.goods[code]
            if not good.cost_based:
                continue
            market = state.markets[code]
            market.unit_cost_minor = unit_cost_minor(state, code)
            market.price_minor = max(1, int(round(market.unit_cost_minor * (1.0 + target_margin))))
    for code, market in state.markets.items():
        market.previous_price_minor = market.price_minor
        market.price_history = [market.price_minor]
        state.cpi_base[code] = market.price_minor


def update_expectation(state: EconomyState, code: str) -> float:
    market = state.markets[code]
    if market.previous_price_minor <= 0:
        return market.expectation
    change = (market.price_minor - market.previous_price_minor) / market.previous_price_minor
    market.expectation = round(max(-1.0, min(1.0, 0.72 * market.expectation + 0.28 * (change * 12.0))), 6)
    return market.expectation


def consumer_price_index(state: EconomyState) -> float:
    total = 0.0
    weight_sum = 0.0
    for code, good in state.goods.items():
        if good.cpi_weight <= 0.0:
            continue
        base = state.cpi_base.get(code) or state.markets[code].price_minor
        total += good.cpi_weight * (state.markets[code].price_minor / max(1, base))
        weight_sum += good.cpi_weight
    return round(total / weight_sum, 6) if weight_sum else 1.0
