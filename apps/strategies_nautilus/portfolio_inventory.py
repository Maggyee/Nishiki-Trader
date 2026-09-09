"""Read-only net-inventory/grid diagnostics; never rounds or creates an order."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.strategies_nautilus.portfolio_preflight import AccountSnapshot, InstrumentRules


@dataclass(frozen=True)
class InventoryDiagnostic:
    sleeve: str
    net_quantity: Decimal
    step_remainder: Decimal
    whole_steps_quantity: Decimal  # diagnostic only, NOT an approved reduced order
    full_exit_blockers: tuple[str, ...]


def inventory_diagnostics(
    account: AccountSnapshot, rules: InstrumentRules, *, limit_price: Decimal
) -> tuple[InventoryDiagnostic, ...]:
    """Expose all untradeable inventory instead of hiding it with rounding.

    Full-exit feasibility here is quantity/notional only, not venue, reservation,
    freshness or risk approval. A nonzero remainder never disappears from equity.
    """
    if not rules.quantity_step.is_finite() or rules.quantity_step <= 0:
        raise ValueError("positive finite quantity step required")
    if not limit_price.is_finite() or limit_price <= 0:
        raise ValueError("positive finite limit price required")
    rows = []
    for sleeve, quantity in account.holdings:
        if not quantity.is_finite() or quantity < 0:
            raise ValueError("invalid net inventory")
        remainder = quantity % rules.quantity_step
        reasons = []
        if quantity:
            if remainder:
                reasons.append("quantity_step")
            if not rules.quantity_min <= quantity <= rules.quantity_max:
                reasons.append("quantity_bounds")
            notional = quantity * limit_price
            if notional < rules.notional_min or (
                rules.notional_max is not None and notional > rules.notional_max
            ):
                reasons.append("notional_bounds")
        rows.append(
            InventoryDiagnostic(sleeve, quantity, remainder, quantity - remainder, tuple(reasons))
        )
    return tuple(rows)
