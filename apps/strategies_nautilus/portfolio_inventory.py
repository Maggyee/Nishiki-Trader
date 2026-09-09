"""Read-only inventory diagnostics and explicit offline exit sizing; no execution."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.strategies_nautilus.portfolio_preflight import AccountSnapshot, InstrumentRules

EXIT_POLICIES = ("exact_v1", "whole_steps_v1")


@dataclass(frozen=True)
class ExitSizing:
    policy: str
    requested_net_quantity: Decimal
    proposed_quantity: Decimal
    retained_if_filled: Decimal


def size_exit(quantity: Decimal, step: Decimal, *, policy: str = "exact_v1") -> ExitSizing:
    """Size one owned reduction, subject to complete subsequent batch preflight.

    Only whole_steps_v1 floors to the trading step. Never cap to max quantity or
    notional, round up to a minimum, split orders or authorize a residual sweep.
    retained_if_filled is a projection, not a settled holding or flatness claim.
    """
    if policy not in EXIT_POLICIES:
        raise ValueError("unknown offline exit policy")
    if not quantity.is_finite() or quantity < 0:
        raise ValueError("invalid net inventory")
    if not step.is_finite() or step <= 0:
        raise ValueError("positive finite quantity step required")
    proposed = quantity if policy == "exact_v1" else quantity - quantity % step
    return ExitSizing(policy, quantity, proposed, quantity - proposed)


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
