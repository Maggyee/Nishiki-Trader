from __future__ import annotations

import pytest

from apps.bridge.signal_event import SignalEvent
from apps.bridge.validators import (
    Authorization,
    ExpiredError,
    UnauthorizedModelError,
    UnauthorizedSourceError,
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
    event = SignalEvent.model_validate(make_payload(source="rogue_agent"))
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
