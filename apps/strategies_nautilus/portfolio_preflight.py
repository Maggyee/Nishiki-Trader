"""Offline batch cash/risk contract; NOT wired to any runner or order endpoint.

Snapshots must come from one reconciled Nautilus account revision. This pure
checker owns no order book, simulates no fills and grants no trading authority.
All money/quantity inputs are finite Decimals. Fees are quote-currency only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")
ONE = Decimal("1")
ACTIVE = {"submitted", "accepted", "partially_filled", "pending_cancel"}
TERMINAL = {"filled", "canceled", "rejected", "expired"}


@dataclass(frozen=True)
class Limits:
    sleeves: tuple[str, ...]
    sleeve_quantity: Decimal
    total_quantity: Decimal
    daily_loss: Decimal
    drawdown_loss: Decimal
    max_age_ns: int


@dataclass(frozen=True)
class InstrumentRules:
    instrument_id: str
    ts_ns: int
    quantity_min: Decimal
    quantity_max: Decimal
    quantity_step: Decimal
    price_min: Decimal
    price_max: Decimal
    price_tick: Decimal
    notional_min: Decimal
    notional_max: Decimal
    fee_rate: Decimal
    fee_currency: str = "USDT"


@dataclass(frozen=True)
class PendingOrder:
    order_id: str
    sleeve: str
    side: str
    remaining: Decimal
    limit_price: Decimal
    status: str


@dataclass(frozen=True)
class AccountSnapshot:
    instrument_id: str
    ts_ns: int
    utc_day_start_ns: int
    reconciled: bool
    total_quote: Decimal  # settled free + locked cash; never equity or free alone
    venue_free_quote: Decimal
    total_base: Decimal
    venue_free_base: Decimal
    holdings: tuple[tuple[str, Decimal], ...]
    pending: tuple[PendingOrder, ...]
    used_order_ids: frozenset[str]  # persisted all-session IDs, including terminal
    mark_price: Decimal
    day_open_equity: Decimal
    peak_equity: Decimal
    risk_latched: bool = False


@dataclass(frozen=True)
class ProposedOrder:
    order_id: str
    sleeve: str
    side: str
    quantity: Decimal
    limit_price: Decimal
    order_type: str = "LIMIT"  # unbounded MARKET deliberately unsupported


@dataclass(frozen=True)
class PreflightResult:
    checks_passed: bool  # never "permission to trade"
    reasons: tuple[str, ...]
    required_quote: Decimal = ZERO
    available_quote: Decimal = ZERO
    required_base: Decimal = ZERO
    available_base: Decimal = ZERO


@dataclass(frozen=True)
class AdmissionCandidate:
    """Consumer-owned proposal plus lineage from an already validated SignalEvent.

    This is not a new bridge protocol. Authorization, side mapping and monotonic
    signal consumption remain the Nautilus consumer's responsibility.
    """

    order: ProposedOrder
    signal_id: str
    ts_event_ns: int
    expires_at_ns: int


@dataclass(frozen=True)
class SkippedOrder:
    order_id: str
    signal_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AdmissionResult:
    selected: tuple[AdmissionCandidate, ...]
    skipped: tuple[SkippedOrder, ...]
    preflight: PreflightResult
    snapshot_ts_ns: int
    evaluated_at_ns: int


def select_funded_batch(
    account: AccountSnapshot,
    rules: InstrumentRules,
    limits: Limits,
    candidates: tuple[AdmissionCandidate, ...],
    *,
    now_ns: int,
) -> AdmissionResult:
    """Greedy deterministic admission, with unchanged whole-batch risk checks.

    Priority: SELL reductions, then event time, frozen sleeve order, order ID.
    Input order, returns and price rankings cannot affect priority. Each trial
    checks the whole selected set, so cash and risk headroom cannot be reused.
    Skips are not queued. This function reserves NOTHING: the eventual Nautilus
    caller must revalidate signals and atomically check/reserve the selected set.
    """

    def blocked(reason: PreflightResult) -> AdmissionResult:
        return AdmissionResult(
            (),
            tuple(SkippedOrder(c.order.order_id, c.signal_id, reason.reasons) for c in candidates),
            reason,
            account.ts_ns,
            now_ns,
        )

    base = check_batch(account, rules, limits, (), now_ns=now_ns)
    if not base.checks_passed:
        return blocked(base)

    # Ambiguous duplicate input must not let caller ordering choose a winner.
    # Malformed priority/lineage also rejects the batch before sorting.
    order_ids, signal_ids, sleeves = set(), set(), set()
    for c in candidates:
        if (
            not isinstance(c.order.order_id, str)
            or not c.order.order_id
            or not isinstance(c.signal_id, str)
            or not c.signal_id
            or not isinstance(c.order.sleeve, str)
            or type(c.ts_event_ns) is not int
            or type(c.expires_at_ns) is not int
            or c.ts_event_ns <= 0
            or c.expires_at_ns <= c.ts_event_ns
        ):
            return blocked(PreflightResult(False, ("invalid_admission_metadata",)))
        if c.order.order_id in order_ids or c.signal_id in signal_ids or c.order.sleeve in sleeves:
            return blocked(PreflightResult(False, ("ambiguous_duplicate_candidate",)))
        order_ids.add(c.order.order_id)
        signal_ids.add(c.signal_id)
        sleeves.add(c.order.sleeve)

    priority = {s: i for i, s in enumerate(limits.sleeves)}
    ordered = sorted(
        candidates,
        key=lambda c: (
            c.order.side != "SELL",
            c.ts_event_ns,
            priority.get(c.order.sleeve, len(priority)),
            c.order.order_id,
        ),
    )
    selected, skipped = [], []
    for c in ordered:
        if c.ts_event_ns > now_ns:
            reasons = ("future_signal",)
        elif now_ns >= c.expires_at_ns:
            reasons = ("expired_signal",)
        else:
            trial = check_batch(
                account, rules, limits, tuple(s.order for s in selected) + (c.order,), now_ns=now_ns
            )
            reasons = trial.reasons
            if trial.checks_passed:
                selected.append(c)
                continue
        skipped.append(SkippedOrder(c.order.order_id, c.signal_id, reasons))

    # Keep the complete-set safety gate even if selection is changed later.
    final = check_batch(account, rules, limits, tuple(c.order for c in selected), now_ns=now_ns)
    if not final.checks_passed:
        return blocked(final)
    return AdmissionResult(tuple(selected), tuple(skipped), final, account.ts_ns, now_ns)


def _number(value: Decimal, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("finite Decimal required")
    if value < ZERO or (positive and value == ZERO):
        raise ValueError("invalid negative/zero value")


def _fresh(ts: int, now: int, age: int) -> bool:
    return type(ts) is int and 0 <= now - ts <= age


def check_batch(
    account: AccountSnapshot,
    rules: InstrumentRules,
    limits: Limits,
    orders: tuple[ProposedOrder, ...],
    *,
    now_ns: int,
) -> PreflightResult:
    """All-or-nothing snapshot check. Caller must serialize check + reservation.

    Pending cancels still reserve; partial fills reserve ONLY their remainder
    (settled totals already include fills). Terminal rows must have zero remainder.
    A sell reserves owned base, never finances a buy before actual settlement.
    Malformed/unreconciled snapshots reject even sells; use a separately reviewed
    emergency reconciliation path, not guessed balances.
    """
    try:
        return _check(account, rules, limits, orders, now_ns)
    except (ValueError, TypeError, ArithmeticError) as exc:
        return PreflightResult(False, (f"invalid_input:{exc}",))


def _check(a, r, limits, orders, now):
    if type(now) is not int or now <= 0 or type(limits.max_age_ns) is not int:
        raise ValueError("integer timestamp/age required")
    if limits.max_age_ns <= 0 or not _fresh(a.ts_ns, now, limits.max_age_ns):
        raise ValueError("stale or future account snapshot")
    if not _fresh(r.ts_ns, now, limits.max_age_ns):
        raise ValueError("stale or future instrument rules")
    day_ns = 86_400_000_000_000
    if type(a.utc_day_start_ns) is not int or a.utc_day_start_ns != now // day_ns * day_ns:
        raise ValueError("missing current UTC day equity baseline")
    if a.reconciled is not True or type(a.risk_latched) is not bool:
        raise ValueError("account not reconciled or unknown risk state")
    if a.instrument_id != "BTCUSDT.BINANCE" or a.instrument_id != r.instrument_id:
        raise ValueError("unsupported/mismatched instrument")
    if r.fee_currency != "USDT":
        raise ValueError("unsupported fee currency")
    if not limits.sleeves or len(set(limits.sleeves)) != len(limits.sleeves):
        raise ValueError("empty/duplicate sleeve limits")
    for value in (
        limits.sleeve_quantity,
        limits.total_quantity,
        limits.daily_loss,
        limits.drawdown_loss,
        r.quantity_min,
        r.quantity_max,
        r.quantity_step,
        r.price_min,
        r.price_max,
        r.price_tick,
        r.notional_min,
        r.notional_max,
        a.mark_price,
        a.day_open_equity,
        a.peak_equity,
    ):
        _number(value, positive=True)
    for value in (a.total_quote, a.venue_free_quote, a.total_base, a.venue_free_base, r.fee_rate):
        _number(value)
    if r.fee_rate >= ONE or r.quantity_min > r.quantity_max or r.price_min > r.price_max:
        raise ValueError("invalid rule bounds")
    if r.notional_min > r.notional_max:
        raise ValueError("invalid notional bounds")
    if a.venue_free_quote > a.total_quote or a.venue_free_base > a.total_base:
        raise ValueError("free exceeds total balance")
    held = dict(a.holdings)
    if len(held) != len(a.holdings) or set(held) != set(limits.sleeves):
        raise ValueError("incomplete/duplicate sleeve attribution")
    for quantity in held.values():
        _number(quantity)
    if sum(held.values(), ZERO) != a.total_base:
        raise ValueError("sleeve holdings do not reconcile to account")
    equity = a.total_quote + a.total_base * a.mark_price
    if a.peak_equity < max(equity, a.day_open_equity):
        raise ValueError("peak equity inconsistent")
    buy_qty = dict.fromkeys(held, ZERO)
    sell_qty = dict.fromkeys(held, ZERO)
    reserved_quote = ZERO
    pending_entry_loss_bound = ZERO
    pending_ids = set()
    for order in a.pending:
        if not order.order_id or order.order_id in pending_ids:
            raise ValueError("duplicate/empty pending order ID")
        pending_ids.add(order.order_id)
        if order.order_id not in a.used_order_ids:
            raise ValueError("pending order missing from persisted IDs")
        if order.sleeve not in held or order.side not in {"BUY", "SELL"}:
            raise ValueError("unknown pending exposure")
        _number(order.remaining)
        _number(order.limit_price, positive=True)
        if order.status in TERMINAL:
            if order.remaining != ZERO:
                raise ValueError("terminal order must have no remaining reservation")
            continue
        if order.status not in ACTIVE or order.remaining == ZERO:
            raise ValueError("unknown/inconsistent active order status")
        if order.side == "BUY":
            reserved_quote += order.remaining * order.limit_price * (ONE + r.fee_rate)
            pending_entry_loss_bound += order.remaining * (
                max(order.limit_price - a.mark_price, ZERO) + order.limit_price * r.fee_rate
            )
            buy_qty[order.sleeve] += order.remaining
        else:
            sell_qty[order.sleeve] += order.remaining
    if reserved_quote > a.total_quote or any(sell_qty[s] > held[s] for s in held):
        raise ValueError("existing reservations exceed settled assets")
    available_quote = min(a.venue_free_quote, a.total_quote - reserved_quote)
    available_base = min(a.venue_free_base, a.total_base - sum(sell_qty.values(), ZERO))
    required_quote = required_base = ZERO
    ids, sleeves = set(), set()
    reasons = []
    has_buy = False
    entry_loss_bound = pending_entry_loss_bound
    for order in orders:
        if not order.order_id or order.order_id in ids or order.order_id in a.used_order_ids:
            raise ValueError("duplicate/reused/empty proposed order ID")
        ids.add(order.order_id)
        if order.sleeve not in held or order.sleeve in sleeves:
            raise ValueError("unknown/repeated proposed sleeve")
        sleeves.add(order.sleeve)
        if order.side not in {"BUY", "SELL"} or order.order_type != "LIMIT":
            raise ValueError("only bounded LIMIT buy/sell checks supported")
        _number(order.quantity, positive=True)
        _number(order.limit_price, positive=True)
        if any(p.sleeve == order.sleeve and p.status in ACTIVE for p in a.pending):
            reasons.append("sleeve_has_pending_order")
        if not r.quantity_min <= order.quantity <= r.quantity_max:
            reasons.append("quantity_bounds")
        if order.quantity % r.quantity_step:
            reasons.append("quantity_step")
        if not r.price_min <= order.limit_price <= r.price_max:
            reasons.append("price_bounds")
        if order.limit_price % r.price_tick:
            reasons.append("price_tick")
        notional = order.quantity * order.limit_price
        if not r.notional_min <= notional <= r.notional_max:
            reasons.append("notional_bounds")
        if order.side == "BUY":
            has_buy = True
            required_quote += notional * (ONE + r.fee_rate)
            # A favorable limit-vs-mark difference cannot finance another
            # entry's fee. This bound is not a guarantee against market gaps.
            entry_loss_bound += order.quantity * max(order.limit_price - a.mark_price, ZERO)
            entry_loss_bound += notional * r.fee_rate
            buy_qty[order.sleeve] += order.quantity
        else:
            required_base += order.quantity
            sell_qty[order.sleeve] += order.quantity
    if required_quote > available_quote:
        reasons.append("insufficient_unreserved_quote")
    if required_base > available_base or any(sell_qty[s] > held[s] for s in held):
        reasons.append("insufficient_unreserved_base")
    if has_buy:
        if a.risk_latched:
            reasons.append("risk_latched")
        if a.day_open_equity - equity >= limits.daily_loss:
            reasons.append("daily_loss_limit")
        if a.peak_equity - equity >= limits.drawdown_loss:
            reasons.append("drawdown_limit")
        if a.day_open_equity - equity + entry_loss_bound >= limits.daily_loss:
            reasons.append("projected_daily_loss_limit")
        if a.peak_equity - equity + entry_loss_bound >= limits.drawdown_loss:
            reasons.append("projected_drawdown_limit")
        if any(held[s] + buy_qty[s] > limits.sleeve_quantity for s in held):
            reasons.append("sleeve_exposure_limit")
        if a.total_base + sum(buy_qty.values(), ZERO) > limits.total_quantity:
            reasons.append("portfolio_exposure_limit")
    return PreflightResult(
        not reasons,
        tuple(dict.fromkeys(reasons)),
        required_quote,
        available_quote,
        required_base,
        available_base,
    )
