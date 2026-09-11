"""Current portfolio planning limits (ADR-015); no account or trading authority."""

from decimal import Decimal

POLICY_ID = "portfolio-risk-v1-20260911"
DAILY_FRACTION = Decimal("0.05")
DAILY_CAP_USDT = Decimal("25")
PEAK_LOSS_USDT = Decimal("250")


def daily_loss_limit(day_open: Decimal, cap: Decimal, fraction: Decimal | None) -> Decimal:
    """Inclusive stop threshold; None is only for explicit historical plan replay."""
    for value in (day_open, cap):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise ValueError("positive finite day-open equity and daily cap required")
    if fraction is None:
        return cap
    if (
        not isinstance(fraction, Decimal)
        or not fraction.is_finite()
        or not 0 < fraction <= DAILY_FRACTION
    ):
        raise ValueError("daily fraction must be positive and at most 5%")
    return min(cap, day_open * fraction)
