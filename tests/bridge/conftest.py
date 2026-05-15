from __future__ import annotations

from pathlib import Path

import pytest

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.bridge.validators import Authorization

REFERENCE_TS_NS = 1_778_760_000_000_000_000  # 2026-05-14T12:00:00Z


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "signal.v1",
        "signal_id": "freqai_v1:BTCUSDT:BINANCE:2026-05-14T12:00:00Z:15m",
        "symbol": "BTCUSDT",
        "venue": "BINANCE",
        "ts_event": REFERENCE_TS_NS,
        "horizon": "15m",
        "side": "buy",
        "score": 0.73,
        "confidence": 0.61,
        "source": "freqai_v1",
        "model_version": "2026-05-14",
        "ttl_seconds": 900,
        "features_hash": None,
        "metadata": {"timeframe": "15m"},
    }
    base.update(overrides)
    return base


@pytest.fixture
def signal_payload() -> dict[str, object]:
    return _payload()


@pytest.fixture
def make_payload():
    return _payload


@pytest.fixture
def signal_event(signal_payload: dict[str, object]) -> SignalEvent:
    return SignalEvent.model_validate(signal_payload)


@pytest.fixture
def auth() -> Authorization:
    return Authorization(
        allowed_sources=frozenset({"freqai_v1"}),
        allowed_model_versions=frozenset({"2026-05-14"}),
    )


@pytest.fixture
def store(tmp_path: Path) -> SignalStore:
    return SignalStore(tmp_path / "signals.db")
