"""Market clearing: who gets the goods and where the money goes.

Buyers pay into an escrow account at the moment of purchase; producers are paid from escrow
at the end of the market cycle in proportion to what they actually supplied. Unfilled demand
either becomes an import (money leaves the city) or stays unmet, which is what a shortage is.
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.companies.model import CompaniesState

from .model import EconomyState, OwnerKind
from .money import transfer

IMPORTABLE = frozenset({"food", "grain", "materials", "components", "electronics", "consumer_goods", "fuel"})
IMPORT_PREMIUM = 1.10
IMPORT_SHORTAGE_RATIO = 0.5      # imports only once local stock is genuinely short


@dataclass(slots=True)
class Purchase:
    code: str
    requested: float
    filled: float
    spent_minor: int = 0
    tax_minor: int = 0
    imported: float = 0.0
    unmet: float = 0.0


def purchase(
    economy: EconomyState,
    *,
    buyer_account_id: str,
    code: str,
    quantity: float,
    vat_rate: float = 0.0,
    treasury_account_id: str = "",
    allow_import: bool = True,
) -> Purchase:
    market = economy.markets.get(code)
    result = Purchase(code=code, requested=quantity, filled=0.0)
    if market is None or quantity <= 0.0:
        return result

    # Everything that has been produced sits in the market's stock until someone buys it.
    # Goods that cannot be stored (electricity, water) have that stock cleared at the end of
    # every market cycle, which is what makes them non-storable in practice.
    good = economy.goods[code]
    available = max(0.0, market.inventory)

    filled = min(quantity, available)
    shortfall = quantity - filled
    imported = 0.0
    short_market = market.inventory < market.demand * IMPORT_SHORTAGE_RATIO
    if shortfall > 1e-9 and allow_import and short_market and code in IMPORTABLE:
        imported = shortfall
        shortfall = 0.0

    unit_price = market.price_minor
    gross = int(round(unit_price * filled + unit_price * IMPORT_PREMIUM * imported))
    tax = int(round(gross * vat_rate)) if vat_rate > 0.0 else 0

    account = economy.accounts.get(buyer_account_id)
    if account is None:
        result.unmet = quantity
        return result
    affordable = account.available()
    if gross + tax > affordable:
        if gross + tax <= 0:
            return result
        scale = max(0.0, affordable / float(gross + tax))
        filled *= scale
        imported *= scale
        gross = int(round(unit_price * filled + unit_price * IMPORT_PREMIUM * imported))
        tax = int(round(gross * vat_rate)) if vat_rate > 0.0 else 0
        shortfall = quantity - filled - imported

    if gross > 0:
        domestic = int(round(unit_price * filled))
        import_value = gross - domestic
        if domestic > 0:
            transfer(economy, buyer_account_id, economy.escrow_account_id, domestic)
        if import_value > 0:
            transfer(economy, buyer_account_id, economy.external_account_id, import_value)
            economy.imports_minor += import_value
    if tax > 0 and treasury_account_id:
        transfer(economy, buyer_account_id, treasury_account_id, tax)

    market.inventory = max(0.0, market.inventory - filled)
    market.transacted += filled + imported
    if imported > 0.0:
        market.supply += imported            # imports are real supply arriving in the city

    result.filled = filled + imported
    result.spent_minor = gross
    result.tax_minor = tax
    result.imported = imported
    result.unmet = max(0.0, shortfall)
    if result.unmet > 0.0:
        market.unmet_demand += result.unmet
    return result


def settle_producers(economy: EconomyState, companies: CompaniesState) -> int:
    """Pay producers from escrow, proportionally to what each supplied this cycle."""

    escrow = economy.accounts.get(economy.escrow_account_id)
    if escrow is None or escrow.balance_minor <= 0:
        for company in companies.companies.values():
            company.supplied_window = 0.0
        return 0

    supplied: dict[str, float] = {}
    for company in companies.companies.values():
        if company.supplied_window > 0.0:
            supplied[company.company_id] = company.supplied_window

    if not supplied:
        for company in companies.companies.values():
            company.supplied_window = 0.0
        return 0

    # Weight by value supplied, not units: a unit of electronics is not a unit of grain.
    weights: dict[str, float] = {}
    total_weight = 0.0
    for company_id, units in supplied.items():
        company = companies.companies[company_id]
        price = economy.markets[company.product_code].price_minor
        weight = units * price
        weights[company_id] = weight
        total_weight += weight
    if total_weight <= 0.0:
        return 0

    pot = escrow.balance_minor
    paid = 0
    for company_id in sorted(weights):
        company = companies.companies[company_id]
        share = int(pot * (weights[company_id] / total_weight))
        if share <= 0:
            continue
        if transfer(economy, economy.escrow_account_id, company.account_id, share):
            company.revenue_minor += share
            paid += share
        company.supplied_window = 0.0
    for company in companies.companies.values():
        company.supplied_window = 0.0
    return paid
