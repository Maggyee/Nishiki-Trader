from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from apps.bridge.signal_event import SignalEvent
from apps.bridge.validators import (
    Authorization,
    ExpiredError,
    SourcePolicy,
    UnauthorizedModelError,
    UnauthorizedSourceError,
    VenueMismatchError,
    is_expired,
    validate,
)


def test_valid_signal_passes(signal_event, auth):
    now_ns = signal_event.ts_event + 60 * 1_000_000_000
    validate(signal_event, auth, now_ns=now_ns)


def test_expired_signal_rejected(signal_event, auth):
    now_ns = signal_event.ts_event + (signal_event.ttl_seconds + 1) * 1_000_000_000
    assert is_expired(signal_event, now_ns=now_ns)
    with pytest.raises(ExpiredError):
        validate(signal_event, auth, now_ns=now_ns)


def test_fresh_signal_not_expired(signal_event):
    now_ns = signal_event.ts_event + (signal_event.ttl_seconds - 1) * 1_000_000_000
    assert not is_expired(signal_event, now_ns=now_ns)


def test_unauthorized_source_rejected(make_payload, auth):
    event = SignalEvent.model_validate(make_payload(source="llm_rogue_agent"))
    with pytest.raises(UnauthorizedSourceError):
        validate(event, auth, now_ns=event.ts_event)


def test_unauthorized_model_version_rejected(make_payload, auth):
    event = SignalEvent.model_validate(make_payload(model_version="0000-00-00"))
    with pytest.raises(UnauthorizedModelError):
        validate(event, auth, now_ns=event.ts_event)


def test_empty_allowlist_rejects_all(signal_event):
    auth = Authorization(allowed_sources=frozenset(), allowed_model_versions=frozenset())
    with pytest.raises(UnauthorizedSourceError):
        validate(signal_event, auth, now_ns=signal_event.ts_event)


# ----- ADR-006 SourcePolicy + Authorization.policies ----------------------


def test_default_source_policy_is_pass_through():
    pol = SourcePolicy()
    assert pol.position_pct_multiplier == 1.0
    assert pol.min_confidence_override is None
    assert pol.dry_run is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"position_pct_multiplier": -0.01},
        {"position_pct_multiplier": 1.5},
        {"min_confidence_override": -0.1},
        {"min_confidence_override": 1.1},
    ],
)
def test_source_policy_rejects_out_of_range(kwargs):
    with pytest.raises(ValueError):
        SourcePolicy(**kwargs)


def test_authorization_default_policies_empty(auth):
    # The ConsumerConfig / Authorization fixtures still work without policies.
    assert auth.policies == {}


def test_authorization_rejects_policy_keys_with_unknown_source_family():
    with pytest.raises(ValueError):
        Authorization(
            allowed_sources=frozenset({"rule_baseline_v1"}),
            allowed_model_versions=frozenset({"ema5-20+rsi14"}),
            policies={("rogue_x", "v1"): SourcePolicy(dry_run=True)},
        )


def test_authorization_accepts_wildcard_policy_keys():
    auth = Authorization(
        allowed_sources=frozenset({"rule_baseline_v1"}),
        allowed_model_versions=frozenset({"ema5-20+rsi14"}),
        policies={
            ("*", "*"): SourcePolicy(position_pct_multiplier=0.5),
        },
    )
    assert auth.policy_for("rule_baseline_v1", "ema5-20+rsi14").position_pct_multiplier == 0.5


def test_policy_for_exact_match_wins_over_wildcards():
    exact = SourcePolicy(position_pct_multiplier=0.1)
    source_wild = SourcePolicy(position_pct_multiplier=0.4)
    model_wild = SourcePolicy(position_pct_multiplier=0.7)
    global_wild = SourcePolicy(position_pct_multiplier=0.9)
    auth = Authorization(
        allowed_sources=frozenset({"rule_baseline_v1"}),
        allowed_model_versions=frozenset({"ema5-20+rsi14"}),
        policies={
            ("rule_baseline_v1", "ema5-20+rsi14"): exact,
            ("rule_baseline_v1", "*"): source_wild,
            ("*", "ema5-20+rsi14"): model_wild,
            ("*", "*"): global_wild,
        },
    )
    assert auth.policy_for("rule_baseline_v1", "ema5-20+rsi14") is exact


def test_policy_for_falls_back_through_source_then_model_then_global():
    source_wild = SourcePolicy(position_pct_multiplier=0.4)
    model_wild = SourcePolicy(position_pct_multiplier=0.7)
    global_wild = SourcePolicy(position_pct_multiplier=0.9)
    auth = Authorization(
        allowed_sources=frozenset({"rule_baseline_v1"}),
        allowed_model_versions=frozenset({"ema5-20+rsi14"}),
        policies={
            ("rule_baseline_v1", "*"): source_wild,
            ("*", "ema5-20+rsi14"): model_wild,
            ("*", "*"): global_wild,
        },
    )
    # source matches → source_wild wins, even though model_wild also matches.
    assert auth.policy_for("rule_baseline_v1", "other-model") is source_wild
    # source does NOT match but model does → model_wild.
    assert auth.policy_for("freqai_other", "ema5-20+rsi14") is model_wild
    # neither matches → global_wild.
    assert auth.policy_for("freqai_other", "other-model") is global_wild


def test_policy_for_returns_default_when_no_match():
    auth = Authorization(
        allowed_sources=frozenset({"rule_baseline_v1"}),
        allowed_model_versions=frozenset({"ema5-20+rsi14"}),
        policies={},
    )
    pol = auth.policy_for("rule_baseline_v1", "ema5-20+rsi14")
    assert pol == SourcePolicy()  # default values


def test_side_score_conflict_rejected_by_validate(make_payload, auth):
    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(make_payload(side="buy", score=-0.2, signal_id="buy-negative"))


def test_validate_checks_expected_venue(make_payload, auth):
    event = SignalEvent.model_validate(make_payload(venue="COINBASE", signal_id="wrong-venue"))
    with pytest.raises(VenueMismatchError):
        validate(event, auth, now_ns=event.ts_event, venue="BINANCE")
