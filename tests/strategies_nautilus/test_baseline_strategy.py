"""Tests for `apps/strategies_nautilus/baseline_strategy.py` (ADR-002 §4.1 + §4.2).

Covers:
- buy / sell / flat → expected `OrderIntent.action` + signed `target_position_pct`.
- §4.1 rejection paths (expired, low confidence, venue mismatch, unauthorized
  source / model_version) return `action="skip"` with a descriptive reason.
- §4.2 kill-switch: engages at -5% day PnL (boundary inclusive), stays engaged
  after partial recovery, blocks long/short but lets `flat` through, clears
  on `on_day_start()`.
- Config range validation rejects out-of-band thresholds.
- Module-level invariant: this file imports no trading API and submits no orders.
"""

from __future__ import annotations

import io
import tokenize

import pytest

from apps.bridge.signal_event import SignalEvent
from apps.bridge.validators import Authorization, SourcePolicy
from apps.strategies_nautilus.baseline_strategy import (
    BaselineSignalStrategy,
    BaselineStrategyConfig,
)


@pytest.fixture
def baseline_config(config):  # reuse ConsumerConfig.venue / auth / min_confidence
    return BaselineStrategyConfig(
        venue=config.venue,
        auth=config.auth,
        min_confidence=config.min_confidence,
        max_position_pct=0.05,
        daily_drawdown_stop_pct=0.05,
    )


@pytest.fixture
def strategy(baseline_config) -> BaselineSignalStrategy:
    return BaselineSignalStrategy(config=baseline_config)


def test_buy_signal_returns_target_long(strategy, signal_event):
    intent = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    assert intent.action == "target_long"
    assert intent.target_position_pct == pytest.approx(0.05)
    assert intent.signal_id == signal_event.signal_id
    assert intent.instrument_id == "BTCUSDT.BINANCE"
    assert intent.reason is None


def test_sell_signal_returns_target_short(strategy, make_payload):
    event = SignalEvent.model_validate(
        make_payload(side="sell", signal_id="sell-1")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "target_short"
    assert intent.target_position_pct == pytest.approx(-0.05)


def test_flat_signal_returns_target_flat(strategy, make_payload):
    event = SignalEvent.model_validate(
        make_payload(side="flat", signal_id="flat-1")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "target_flat"
    assert intent.target_position_pct == 0.0


def test_expired_signal_returns_skip(strategy, signal_event):
    expired_now = signal_event.ts_event + (signal_event.ttl_seconds + 1) * 1_000_000_000
    intent = strategy.decide(signal_event, now_ns=expired_now)
    assert intent.action == "skip"
    assert intent.target_position_pct == 0.0
    assert intent.reason is not None and intent.reason.startswith("expired")


def test_low_confidence_signal_returns_skip(strategy, make_payload):
    event = SignalEvent.model_validate(
        make_payload(confidence=0.10, signal_id="lowconf-1")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "skip"
    assert intent.reason is not None
    assert intent.reason.startswith("reject_low_confidence")


def test_venue_mismatch_returns_skip(strategy, make_payload):
    event = SignalEvent.model_validate(
        make_payload(venue="COINBASE", signal_id="venue-1")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "skip"
    assert intent.reason is not None and intent.reason.startswith("reject_venue")


def test_unauthorized_source_returns_skip(strategy, make_payload):
    event = SignalEvent.model_validate(
        make_payload(source="llm_rogue", signal_id="src-1")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "skip"
    assert intent.reason is not None
    assert intent.reason.startswith("reject_unauthorized_source")


def test_unauthorized_model_returns_skip(strategy, make_payload):
    event = SignalEvent.model_validate(
        make_payload(model_version="9999-99-99", signal_id="model-1")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "skip"
    assert intent.reason is not None
    assert intent.reason.startswith("reject_unauthorized_model")


def test_kill_switch_engages_at_threshold_boundary(strategy):
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_500.0)
    assert strategy.kill_switch_engaged is True
    assert "daily_pnl" in (strategy.kill_switch_reason or "")


def test_kill_switch_does_not_engage_above_threshold(strategy):
    # -4.99% loss: just shy of the -5% threshold
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_501.0)
    assert strategy.kill_switch_engaged is False
    assert strategy.kill_switch_reason is None


def test_kill_switch_engages_below_threshold(strategy):
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_000.0)
    assert strategy.kill_switch_engaged is True


def test_kill_switch_blocks_buy_signal(strategy, signal_event):
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_500.0)
    intent = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    assert intent.action == "skip"
    assert intent.reason is not None and intent.reason.startswith("kill_switch")


def test_kill_switch_blocks_sell_signal(strategy, make_payload):
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_500.0)
    event = SignalEvent.model_validate(
        make_payload(side="sell", signal_id="ks-sell")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "skip"
    assert intent.reason is not None and intent.reason.startswith("kill_switch")


def test_kill_switch_allows_flat_signal(strategy, make_payload):
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_500.0)
    event = SignalEvent.model_validate(
        make_payload(side="flat", signal_id="ks-flat")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "target_flat"
    assert intent.target_position_pct == 0.0


def test_kill_switch_sticks_after_recovery(strategy):
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_400.0)
    assert strategy.kill_switch_engaged is True
    # Equity bounces back to -3%; kill-switch must NOT clear mid-day.
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_700.0)
    assert strategy.kill_switch_engaged is True


def test_on_day_start_clears_kill_switch(strategy):
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_400.0)
    assert strategy.kill_switch_engaged is True
    strategy.on_day_start()
    assert strategy.kill_switch_engaged is False
    assert strategy.kill_switch_reason is None


def test_on_account_update_ignores_zero_equity_open(strategy):
    strategy.on_account_update(equity_open=0.0, equity_now=-500.0)
    assert strategy.kill_switch_engaged is False


def test_on_account_update_ignores_negative_equity_open(strategy):
    strategy.on_account_update(equity_open=-1.0, equity_now=-2.0)
    assert strategy.kill_switch_engaged is False


def test_decide_is_idempotent(strategy, signal_event):
    a = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    b = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    assert a == b


def test_instrument_id_format(strategy, make_payload):
    event = SignalEvent.model_validate(
        make_payload(symbol="ETHUSDT", signal_id="eth-1")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.instrument_id == "ETHUSDT.BINANCE"


def test_intent_target_pct_tracks_config(make_payload, baseline_config, signal_event):
    cfg = BaselineStrategyConfig(
        venue=baseline_config.venue,
        auth=baseline_config.auth,
        min_confidence=baseline_config.min_confidence,
        max_position_pct=0.10,
        daily_drawdown_stop_pct=0.05,
    )
    strategy = BaselineSignalStrategy(config=cfg)
    intent = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    assert intent.target_position_pct == pytest.approx(0.10)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_confidence": 0.0},
        {"min_confidence": 1.5},
        {"min_confidence": -0.1},
        {"max_position_pct": 0.0},
        {"max_position_pct": 1.5},
        {"daily_drawdown_stop_pct": 0.0},
        {"daily_drawdown_stop_pct": 1.5},
    ],
)
def test_config_rejects_out_of_range_thresholds(kwargs, config):
    base = {
        "venue": config.venue,
        "auth": config.auth,
        "min_confidence": 0.55,
        "max_position_pct": 0.05,
        "daily_drawdown_stop_pct": 0.05,
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        BaselineStrategyConfig(**base)


def _strip_comments_and_strings(source: str) -> str:
    """Return source code with comments and string literals removed.

    Keeps the forbidden-token check focused on executable code — docstrings
    that legitimately discuss the future Nautilus wrapper must not trip it.
    """
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return " ".join(
        tok.string
        for tok in tokens
        if tok.type not in (tokenize.COMMENT, tokenize.STRING)
    )


def test_baseline_strategy_module_has_no_trading_api_calls():
    from apps.strategies_nautilus import baseline_strategy

    with open(baseline_strategy.__file__, encoding="utf-8") as f:
        text = f.read()
    code = _strip_comments_and_strings(text)
    for forbidden in (
        "nautilus_trader",
        "freqtrade",
        "requests.",
        "httpx.",
        "ccxt.",
        "binance",
        "submit_order",
        "ExecutionEngine",
    ):
        assert forbidden not in code, (
            f"forbidden token {forbidden!r} found in baseline_strategy.py "
            "executable code — decision layer must not touch trading APIs"
        )


def test_minimum_authorization_required(make_payload, config):
    # An empty allow-list rejects everything → strategy emits skip.
    empty_auth = Authorization(
        allowed_sources=frozenset(),
        allowed_model_versions=frozenset(),
    )
    cfg = BaselineStrategyConfig(
        venue=config.venue,
        auth=empty_auth,
        min_confidence=0.55,
    )
    strategy = BaselineSignalStrategy(config=cfg)
    event = SignalEvent.model_validate(make_payload())
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "skip"
    assert intent.reason is not None
    assert intent.reason.startswith("reject_unauthorized_source")


# ----- ADR-006 source policy --------------------------------------------


def _auth_with_policy(config, policy: SourcePolicy) -> Authorization:
    return Authorization(
        allowed_sources=config.auth.allowed_sources,
        allowed_model_versions=config.auth.allowed_model_versions,
        policies={("freqai_v1", "2026-05-14"): policy},
    )


def _strategy_with_policy(config, policy: SourcePolicy) -> BaselineSignalStrategy:
    cfg = BaselineStrategyConfig(
        venue=config.venue,
        auth=_auth_with_policy(config, policy),
        min_confidence=0.55,
        max_position_pct=0.05,
        daily_drawdown_stop_pct=0.05,
    )
    return BaselineSignalStrategy(config=cfg)


def test_policy_multiplier_scales_target_position_pct(config, signal_event):
    strategy = _strategy_with_policy(config, SourcePolicy(position_pct_multiplier=0.2))
    intent = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    assert intent.action == "target_long"
    assert intent.target_position_pct == pytest.approx(0.05 * 0.2)
    assert intent.dry_run is False


def test_policy_multiplier_zero_zeroes_target_but_keeps_action(config, signal_event):
    strategy = _strategy_with_policy(config, SourcePolicy(position_pct_multiplier=0.0))
    intent = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    assert intent.action == "target_long"
    assert intent.target_position_pct == 0.0
    assert intent.dry_run is False


def test_policy_min_confidence_override_can_only_tighten(config, make_payload):
    # Override is *less* strict than strategy floor (0.55) — must NOT relax.
    strategy = _strategy_with_policy(
        config, SourcePolicy(min_confidence_override=0.30)
    )
    event = SignalEvent.model_validate(
        make_payload(confidence=0.50, signal_id="conf-relax")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    # Strategy floor 0.55 still wins → consumer.evaluate rejected first.
    assert intent.action == "skip"
    assert intent.reason is not None
    assert intent.reason.startswith("reject_low_confidence")


def test_policy_min_confidence_override_tighter_than_strategy_floor(config, make_payload):
    strategy = _strategy_with_policy(
        config, SourcePolicy(min_confidence_override=0.80)
    )
    # confidence > strategy floor (0.55) but < override (0.80).
    event = SignalEvent.model_validate(
        make_payload(confidence=0.70, signal_id="conf-policy")
    )
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "skip"
    assert intent.reason is not None
    assert intent.reason.startswith("reject_low_confidence_policy")
    assert "0.700" in intent.reason
    assert "0.800" in intent.reason


def test_policy_dry_run_marks_intent_but_keeps_action(config, signal_event):
    strategy = _strategy_with_policy(
        config, SourcePolicy(position_pct_multiplier=0.5, dry_run=True)
    )
    intent = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    assert intent.action == "target_long"
    assert intent.target_position_pct == pytest.approx(0.025)
    assert intent.dry_run is True
    # Reason is None — dry_run is a flag, not a rejection reason.
    assert intent.reason is None


def test_policy_dry_run_flat_also_marked(config, make_payload):
    strategy = _strategy_with_policy(config, SourcePolicy(dry_run=True))
    event = SignalEvent.model_validate(make_payload(side="flat", signal_id="flat-dry"))
    intent = strategy.decide(event, now_ns=event.ts_event)
    assert intent.action == "target_flat"
    assert intent.dry_run is True


def test_kill_switch_outranks_dry_run(config, signal_event):
    strategy = _strategy_with_policy(config, SourcePolicy(dry_run=True))
    # Engage kill-switch first.
    strategy.on_account_update(equity_open=10_000.0, equity_now=9_500.0)
    intent = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    # Kill-switch wins; dry_run never applied because we took the skip path.
    assert intent.action == "skip"
    assert intent.dry_run is False
    assert intent.reason is not None
    assert intent.reason.startswith("kill_switch")


def test_policy_wildcard_applies_when_exact_missing(config, signal_event):
    auth = Authorization(
        allowed_sources=config.auth.allowed_sources,
        allowed_model_versions=config.auth.allowed_model_versions,
        policies={("freqai_v1", "*"): SourcePolicy(position_pct_multiplier=0.1)},
    )
    cfg = BaselineStrategyConfig(
        venue=config.venue,
        auth=auth,
        min_confidence=0.55,
        max_position_pct=0.05,
    )
    strategy = BaselineSignalStrategy(config=cfg)
    intent = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    assert intent.action == "target_long"
    assert intent.target_position_pct == pytest.approx(0.005)


def test_no_policy_means_full_position(config, signal_event):
    # Sanity: ADR-006 must not change behaviour when policies is empty.
    strategy = _strategy_with_policy(config, SourcePolicy())
    intent = strategy.decide(signal_event, now_ns=signal_event.ts_event)
    assert intent.action == "target_long"
    assert intent.target_position_pct == pytest.approx(0.05)
    assert intent.dry_run is False
