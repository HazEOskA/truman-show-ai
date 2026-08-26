"""Economy: money conservation, price formation, clearing and the labour market."""

from __future__ import annotations

from hydra.agents.model import AgentsState, Employment
from hydra.companies.model import CompaniesState
from hydra.economy.clearing import purchase
from hydra.economy.demand import estimate_daily_demand
from hydra.economy.model import EconomyState, OwnerKind
from hydra.economy.money import mint, transfer
from hydra.economy.pricing import next_price_minor, unit_cost_minor
from hydra.kernel.clock import TICKS_PER_DAY
from hydra.world import create_world

from conftest import small_config


def total_money(economy: EconomyState) -> int:
    return sum(account.balance_minor for account in economy.accounts.values())


def test_money_is_conserved_across_a_simulated_day(world):
    economy = world.state.domain(EconomyState)
    before = total_money(economy)
    world.kernel.run(TICKS_PER_DAY)
    after = total_money(economy)
    # The only legitimate leak is trade with the rest of the world, which has its own account.
    assert before == after, f"money changed by {after - before} minor units without minting"


def test_transfer_respects_balances_and_overdraft(world):
    economy = world.state.domain(EconomyState)
    source = economy.open_account("probe_a", OwnerKind.PERSON, balance_minor=1_000, overdraft_minor=200)
    target = economy.open_account("probe_b", OwnerKind.PERSON, balance_minor=0)

    assert transfer(economy, source.account_id, target.account_id, 900) is True
    assert source.balance_minor == 100 and target.balance_minor == 900
    assert transfer(economy, source.account_id, target.account_id, 500) is False, "overdraft is a limit"
    assert transfer(economy, source.account_id, target.account_id, 300) is True
    assert source.balance_minor == -200


def test_minting_is_the_only_way_money_appears(world):
    economy = world.state.domain(EconomyState)
    account = economy.open_account("probe_mint", OwnerKind.CENTRAL_BANK)
    before = economy.money_supply_minor
    mint(economy, account.account_id, 5_000)
    assert economy.money_supply_minor == before + 5_000


def test_prices_follow_unit_costs(world):
    economy = world.state.domain(EconomyState)
    market = economy.markets["food"]
    market.unit_cost_minor = unit_cost_minor(economy, "food")
    market.supply = 100.0
    market.demand = 100.0

    # An input cost shock pushes the price up, but never faster than the cap allows.
    market.unit_cost_minor *= 3
    stepped = next_price_minor(economy, "food", target_margin=0.18, change_cap=0.025, drift=0.35)
    assert stepped > market.price_minor
    assert stepped <= market.price_minor + max(1.0, market.price_minor * 0.025) + 1


def test_excess_demand_raises_price_and_excess_supply_lowers_it(world):
    economy = world.state.domain(EconomyState)
    market = economy.markets["consumer_goods"]
    market.unit_cost_minor = 1
    market.supply, market.demand = 100.0, 300.0
    up = next_price_minor(economy, "consumer_goods", target_margin=0.18, change_cap=0.05, drift=0.35)
    market.supply, market.demand = 300.0, 100.0
    down = next_price_minor(economy, "consumer_goods", target_margin=0.18, change_cap=0.05, drift=0.35)
    assert up > market.price_minor > down


def test_a_market_with_no_trade_does_not_drift(world):
    economy = world.state.domain(EconomyState)
    market = economy.markets["electronics"]
    market.supply = market.demand = 0.0
    assert next_price_minor(economy, "electronics", target_margin=0.18, change_cap=0.05, drift=0.35) == market.price_minor


def test_purchase_is_limited_by_stock_and_by_money(world):
    economy = world.state.domain(EconomyState)
    market = economy.markets["food"]
    market.inventory = 10.0
    buyer = economy.open_account("probe_buyer", OwnerKind.PERSON, balance_minor=market.price_minor * 3)

    result = purchase(economy, buyer_account_id=buyer.account_id, code="food", quantity=100.0, allow_import=False)
    assert result.filled <= 10.0
    assert result.filled <= 3.0 + 1e-6, "cannot buy more food than the money on hand"
    assert result.unmet > 0


def test_demand_estimate_expands_through_the_bill_of_materials(world):
    economy = world.state.domain(EconomyState)
    demand = estimate_daily_demand(economy, residents=10_000, households=4_000, employed=4_600)
    assert demand["food"] > 10_000 * 0.9
    # Nobody eats grain directly, but the city needs it to make food.
    assert demand["grain"] > 0
    assert demand["electricity"] > demand["food"], "power feeds every other process"


def test_employment_and_wages_flow_to_people(world):
    agents = world.state.domain(AgentsState)
    economy = world.state.domain(EconomyState)
    worker = next(
        p for p in agents.people.values()
        if p.employment is Employment.EMPLOYED and p.wage_minor > 0
    )
    before = economy.balance(worker.account_id)
    world.kernel.run(TICKS_PER_DAY + 1)
    assert economy.balance(worker.account_id) != before, "a day of work must move money"


def test_companies_have_staff_matched_to_their_labour_needs(world):
    companies = world.state.domain(CompaniesState)
    firms = companies.active()
    assert firms
    staffed = sum(1 for c in firms if 0.5 <= c.headcount() / max(1, c.headcount_target) <= 2.0)
    assert staffed > len(firms) * 0.75, "genesis should not open a city of over- or under-staffed firms"
