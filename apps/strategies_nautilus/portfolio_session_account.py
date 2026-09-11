"""Native CASH lock calculation for one known offline engineering order.

The native manager supplies original order quantity after partial fills. This
isolated extension resolves the sole matching native order and delegates locking
of its remaining quantity to CashAccount. No remote balances are assigned.
"""

from nautilus_trader.accounting.accounts.cash import CashAccount


class SessionCashAccount(CashAccount):
    def __init__(self, event, *, cache):
        super().__init__(event, calculate_account_state=True)
        self.session_cache = cache

    def calculate_balance_locked(
        self, instrument, side, quantity, price, use_quote_for_inverse=False
    ):
        candidates = [
            o
            for o in self.session_cache.orders()
            if o.is_open
            and o.instrument_id == instrument.id
            and o.side == side
            and o.quantity == quantity
            and o.price == price
        ]
        if (
            len(candidates) != 1
            or str(candidates[0].strategy_id) != "TESTNET-SESSION-TS"
            or candidates[0].account_id != self.id
            or instrument.is_inverse
        ):
            raise ValueError("one attributable native session order required for CASH locks")
        return super().calculate_balance_locked(
            instrument, side, candidates[0].leaves_qty, price, use_quote_for_inverse
        )


def restore_session_cash_account(account, cache):
    restored = SessionCashAccount(account.events[0], cache=cache)
    for event in account.events[1:]:
        restored.apply(event)
    return restored
