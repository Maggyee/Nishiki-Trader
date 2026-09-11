"""Read-only risk observations between native checkpoints; never a restart permit.

Values come from native account snapshots and bid quotes, not an inferred fill
ledger. Sparse observations can establish a breach, never prove its absence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.events import AccountState

from apps.ops.portfolio_execution_plan import preflight_limits
from apps.strategies_nautilus.portfolio_adapter_checkpoint import NUMERIC_MODE
from apps.strategies_nautilus.portfolio_recovery import (
    SERIALIZER,
    reconstruct_native,
    verify_checkpoint,
)
from apps.strategies_nautilus.portfolio_risk_policy import DAILY_FRACTION, POLICY_ID
from apps.strategies_nautilus.portfolio_stream import SourceBinding
from apps.strategies_nautilus.portfolio_venue import _decimal, _unique_object

DAY_NS = 86_400_000_000_000


class DowntimeRiskError(ValueError):
    pass


def _balances(event, account_id):
    if (
        not isinstance(event, AccountState)
        or str(event.account_id) != account_id
        or event.account_type.name != "CASH"
    ):
        raise DowntimeRiskError("dedicated native CASH snapshot required")
    result = {}
    for row in event.balances:
        code = row.currency.code
        if code in result or code not in {"BTC", "USDT"}:
            raise DowntimeRiskError("duplicate or unsupported native balance")
        result[code] = tuple(v.as_decimal() for v in (row.total, row.free, row.locked))
    if set(result) != {"BTC", "USDT"} or any(
        total < 0 or free < 0 or locked < 0 or total != free + locked
        for total, free, locked in result.values()
    ):
        raise DowntimeRiskError("invalid native account balances")
    return result


def review_downtime_risk(
    before_raw: bytes,
    after_raw: bytes,
    history_raw: bytes,
    *,
    source: SourceBinding,
    expected_before_sha256: str,
    expected_after_sha256: str,
    max_gap_ns: int = 1_000_000_000,
):
    """Inspect a single UTC day's recorded path; original state is never changed.

    Checkpoint/source hashes bind selected inputs, not their authentication. Both
    checkpoint endpoints must match recorded balances exactly, including locks.
    Cross-day reviews require qualified new day-open evidence and are rejected.
    """
    before_hash, after_hash = (hashlib.sha256(raw).hexdigest() for raw in (before_raw, after_raw))
    if (before_hash, after_hash) != (expected_before_sha256, expected_after_sha256):
        raise DowntimeRiskError("selected checkpoint digest mismatch")
    if type(max_gap_ns) is not int or not 0 < max_gap_ns <= 60_000_000_000:
        raise DowntimeRiskError("invalid observation gap bound")
    if (
        source.endpoint not in {"https://api.binance.com", "https://testnet.binance.vision"}
        or not isinstance(source.account_uid, str)
        or not source.account_uid
        or len(source.key_sha256) != 64
        or any(c not in "0123456789abcdef" for c in source.key_sha256)
    ):
        raise DowntimeRiskError("explicit source binding required")
    before, after = (verify_checkpoint(raw) for raw in (before_raw, after_raw))
    if before["state"] != after["state"] or before["native"]["anchor"] != after["native"]["anchor"]:
        raise DowntimeRiskError("recovery changed strategy state or account anchor")
    state = before["state"]
    start, end = before["native"]["ts_ns"], after["native"]["ts_ns"]
    if type(start) is not int or type(end) is not int or not 0 < start < end:
        raise DowntimeRiskError("invalid downtime interval")
    day = start // DAY_NS * DAY_NS
    if (
        end // DAY_NS * DAY_NS != day
        or type(state.get("day_ns")) is not int
        or state["day_ns"] != day
    ):
        raise DowntimeRiskError("UTC rollover or missing qualified day-open baseline")
    if type(state.get("risk_latched")) is not bool:
        raise DowntimeRiskError("persisted boolean risk latch required")
    day_open, peak = (_decimal(state[key]) for key in ("day_open", "peak"))
    if day_open <= 0 or peak < day_open:
        raise DowntimeRiskError("invalid persisted day-open/peak equity")
    account_id = before["native"]["anchor"]["native_account_id"]
    if before["native"]["anchor"]["venue_uid"] != source.account_uid:
        raise DowntimeRiskError("checkpoint/source account mismatch")
    endpoints = []
    for wrapped in (before, after):
        _, account, _, _ = reconstruct_native(wrapped["native"], venue_id_mode=NUMERIC_MODE)
        endpoints.append(_balances(account.events[-1], account_id))
    history = json.loads(history_raw, object_pairs_hook=_unique_object)
    if (
        not isinstance(history, dict)
        or set(history)
        != {"schema_version", "input_sha256", "output_sha256", "source", "observations"}
        or history["schema_version"] != "portfolio.downtime_risk.v1"
    ):
        raise DowntimeRiskError("unsupported downtime history schema")
    if (history["input_sha256"], history["output_sha256"], history["source"]) != (
        before_hash,
        after_hash,
        asdict(source),
    ):
        raise DowntimeRiskError("history checkpoint/source binding mismatch")
    rows = history["observations"]
    if not isinstance(rows, list) or not 2 <= len(rows) <= 10000:
        raise DowntimeRiskError("bounded observations including both endpoints required")
    if rows[0]["ts_ns"] != start or rows[-1]["ts_ns"] != end:
        raise DowntimeRiskError("history must include exact checkpoint endpoints")
    limits = preflight_limits()
    daily_limit = day_open * DAILY_FRACTION
    effective_limit = limits.effective_daily_loss(day_open)
    previous_ts, previous_account_ts, previous_quote_ts = None, None, None
    gaps, samples, first_breaches = [], [], {}
    seen_accounts = {}
    seen_quotes = {}
    for index, row in enumerate(rows):
        if set(row) != {"ts_ns", "account_event", "quote"}:
            raise DowntimeRiskError("unsupported downtime observation")
        ts = row["ts_ns"]
        if (
            type(ts) is not int
            or not start <= ts <= end
            or (previous_ts is not None and ts <= previous_ts)
        ):
            raise DowntimeRiskError("observations must be strictly ordered inside downtime")
        account = SERIALIZER.deserialize(row["account_event"].encode())
        quote = SERIALIZER.deserialize(row["quote"].encode())
        balances = _balances(account, account_id)
        if not isinstance(quote, QuoteTick) or str(quote.instrument_id) != "BTCUSDT.BINANCE":
            raise DowntimeRiskError("native BTCUSDT bid quote required")
        if (
            not 0 <= ts - account.ts_event <= 60_000_000_000
            or not 0 <= ts - quote.ts_event <= max_gap_ns
            or account.ts_init > ts
            or quote.ts_init > ts
        ):
            raise DowntimeRiskError("stale or future account/quote observation")
        if (previous_account_ts is not None and account.ts_event < previous_account_ts) or (
            previous_quote_ts is not None and quote.ts_event < previous_quote_ts
        ):
            raise DowntimeRiskError("native account/quote time regressed")
        # Reusing a snapshot is fine; changing the contents under its identity is not.
        account_key, quote_key = str(account.id), (quote.ts_event, quote.ts_init)
        for seen, key, value in (
            (seen_accounts, account_key, row["account_event"]),
            (seen_quotes, quote_key, row["quote"]),
        ):
            if key in seen and seen[key] != value:
                raise DowntimeRiskError("conflicting native observation replay")
            seen[key] = value
        bid, ask = quote.bid_price.as_decimal(), quote.ask_price.as_decimal()
        if (
            bid <= 0
            or ask < bid
            or quote.bid_size.as_decimal() <= 0
            or quote.ask_size.as_decimal() <= 0
        ):
            raise DowntimeRiskError("invalid bid/ask quote")
        if (
            index == 0
            and balances != endpoints[0]
            or index == len(rows) - 1
            and balances != endpoints[1]
        ):
            raise DowntimeRiskError("history/native checkpoint balance mismatch")
        equity = balances["USDT"][0] + balances["BTC"][0] * bid
        if index == 0 and equity > peak:
            raise DowntimeRiskError("persisted peak below starting marked equity")
        peak = max(peak, equity)
        if previous_ts is not None and ts - previous_ts > max_gap_ns:
            gaps.append({"start_ns": previous_ts, "end_ns": ts})
        daily_loss, drawdown = day_open - equity, peak - equity
        for name, loss, threshold in (
            ("daily_5pct", daily_loss, daily_limit),
            ("planning_daily", daily_loss, effective_limit),
            ("planning_drawdown", drawdown, limits.drawdown_loss),
        ):
            if loss >= threshold and name not in first_breaches:
                first_breaches[name] = {
                    "ts_ns": ts,
                    "equity_usdt": str(equity),
                    "loss_usdt": str(loss),
                    "limit_usdt": str(threshold),
                }
        samples.append(equity)
        previous_ts, previous_account_ts, previous_quote_ts = ts, account.ts_event, quote.ts_event
    stop = bool(first_breaches) or state["risk_latched"] or bool(state.get("halt_reason"))
    return {
        "status": "observed_stop" if stop else "observed_no_breach",
        "runtime_ready": False,
        "real_account_verified": False,
        "downtime_history_complete": False,
        "downtime_risk_review_required": True,
        "input_sha256": before_hash,
        "output_sha256": after_hash,
        "history_sha256": hashlib.sha256(history_raw).hexdigest(),
        "source": asdict(source),
        "state_sha256": before["sha256"],
        "prior_risk_latched": state["risk_latched"],
        "observed_stop_required": stop,
        "incident_review_required": stop,
        "first_breaches": first_breaches,
        "observations": len(rows),
        "observation_gaps": gaps,
        "minimum_observed_equity_usdt": str(min(samples)),
        "ending_equity_usdt": str(samples[-1]),
        "observed_peak_usdt": str(peak),
        "daily_5pct_limit_usdt": str(daily_limit),
        "risk_policy_id": POLICY_ID,
        "checkpoint_policy_qualified": False,
        "planning_daily_cap_usdt": str(limits.daily_loss),
        "planning_daily_limit_usdt": str(effective_limit),
        "planning_daily_exceeds_5pct": effective_limit > daily_limit,
        "blocking_reasons": [
            "sampled_history_cannot_prove_complete_downtime",
            "runtime_policy_and_source_require_qualification",
        ]
        + (["observed_or_persisted_stop_requires_incident_review"] if stop else [])
        + (["observation_gaps"] if gaps else []),
    }
