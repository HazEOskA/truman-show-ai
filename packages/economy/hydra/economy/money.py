"""Money movement primitives.

Every currency unit that exists was created explicitly. Transfers are the only way money
moves, and they either fully succeed or do nothing — no partial writes, no negative balances
below an account's overdraft.
"""

from __future__ import annotations

from hydra.kernel.errors import ActionRejected

from .model import Account, EconomyState


def transfer(state: EconomyState, source_id: str, target_id: str, amount_minor: int, *, allow_overdraft: bool = True) -> bool:
    if amount_minor <= 0:
        return True
    source = state.accounts.get(source_id)
    target = state.accounts.get(target_id)
    if source is None or target is None or source.blocked:
        return False
    limit = source.available() if allow_overdraft else source.balance_minor
    if limit < amount_minor:
        return False
    source.balance_minor -= amount_minor
    target.balance_minor += amount_minor
    state.transactions += 1
    state.volume_minor += amount_minor
    return True


def require_transfer(state: EconomyState, source_id: str, target_id: str, amount_minor: int, reason: str) -> None:
    if not transfer(state, source_id, target_id, amount_minor):
        raise ActionRejected("insufficient_funds", f"{reason}: {amount_minor} from {source_id}")


def mint(state: EconomyState, target_id: str, amount_minor: int) -> None:
    """Central bank money creation. The only legitimate source of new units."""

    account = state.accounts.get(target_id)
    if account is None or amount_minor <= 0:
        return
    account.balance_minor += amount_minor
    state.money_supply_minor += amount_minor


def burn(state: EconomyState, source_id: str, amount_minor: int) -> None:
    account = state.accounts.get(source_id)
    if account is None or amount_minor <= 0:
        return
    account.balance_minor -= amount_minor
    state.money_supply_minor -= amount_minor


def net_worth(state: EconomyState, account_id: str) -> int:
    account: Account | None = state.accounts.get(account_id)
    if account is None:
        return 0
    debt = sum(l.outstanding_minor for l in state.loans.values() if l.borrower_id == account.owner_id)
    return account.balance_minor - debt
