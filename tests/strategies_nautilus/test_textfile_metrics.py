"""Tests for the Prometheus textfile collector exporter.

The exporter is a secondary observability surface (ADR-001 §6 observability
stack, brought forward to Phase 3 entry). Its bundle-side counterparts —
``heartbeat.jsonl``, ``alerts.log``, ``run_manifest.json``, parquet sidecars
— are not affected by these tests.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.strategies_nautilus.runners.testnet_runner import (
    GitState,
    LongRunningTestnetSettings,
    StartupSettings,
    TestnetRuntimeTelemetry,
    run_long_running_testnet,
)
from apps.strategies_nautilus.runners.textfile_metrics import (
    PrometheusTextfileWriter,
    render_textfile_metrics,
    write_textfile_atomic,
)


def _make_settings(tmp_path: Path) -> LongRunningTestnetSettings:
    return LongRunningTestnetSettings(
        output_root=tmp_path / "out",
        instrument_ids=("BTCUSDT.BINANCE",),
        starting_balance=10_000.0,
        max_run_seconds=60.0,
        daily_loss_limit_pct=0.05,
    )


def _make_sample(
    *,
    ts: datetime | None = None,
    daily_pnl: float = 0.0,
    open_orders: int | None = 0,
    open_positions: int | None = 0,
    last_bar_ns: int | None = 1_700_000_000_000_000_000,
    last_signal_ns: int | None = 1_700_000_000_500_000_000,
    ws_connected: bool = True,
    ws_reconnect_count: int = 0,
    exchange_error_count: int = 0,
    account_total_usdt: float | None = 10_000.0,
) -> TestnetRuntimeTelemetry:
    return TestnetRuntimeTelemetry(
        ts=ts or datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC),
        daily_pnl=daily_pnl,
        exchange_error_count=exchange_error_count,
        ws_reconnect_count=ws_reconnect_count,
        account_total_usdt=account_total_usdt,
        open_orders=open_orders,
        open_positions=open_positions,
        last_bar_ns=last_bar_ns,
        last_signal_ns=last_signal_ns,
        ws_connected=ws_connected,
    )


def test_render_textfile_metrics_emits_help_and_type_for_every_metric(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    sample = _make_sample()

    content = render_textfile_metrics(
        sample=sample,
        kind="testnet",
        run_id="20260520-120000Z-abcd1234",
        settings=settings,
        alert_counts={},
    )

    expected_help_count = sum(1 for line in content.splitlines() if line.startswith("# HELP "))
    expected_type_count = sum(1 for line in content.splitlines() if line.startswith("# TYPE "))
    assert expected_help_count == expected_type_count
    # One HELP/TYPE pair per declared metric, with at least the core 13 metrics.
    assert expected_help_count >= 13


def test_render_textfile_metrics_includes_run_identity_labels(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    sample = _make_sample()
    content = render_textfile_metrics(
        sample=sample,
        kind="testnet",
        run_id="20260520-120000Z-abcd1234",
        settings=settings,
        alert_counts={},
    )

    assert 'kind="testnet"' in content
    assert 'run_id="20260520-120000Z-abcd1234"' in content
    assert "trader_canary_info" in content
    assert "trader_canary_heartbeat_timestamp_seconds" in content


def test_render_textfile_metrics_omits_optional_fields_when_none(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    sample = _make_sample(
        open_orders=None,
        open_positions=None,
        last_bar_ns=None,
        last_signal_ns=None,
        account_total_usdt=None,
    )

    content = render_textfile_metrics(
        sample=sample,
        kind="testnet",
        run_id="r1",
        settings=settings,
        alert_counts={},
    )

    metric_lines = [
        line for line in content.splitlines()
        if line and not line.startswith("#")
    ]
    metric_names = {line.split("{", 1)[0] for line in metric_lines}
    assert "trader_canary_open_orders" not in metric_names
    assert "trader_canary_open_positions" not in metric_names
    assert "trader_canary_last_bar_timestamp_seconds" not in metric_names
    assert "trader_canary_last_signal_timestamp_seconds" not in metric_names
    assert "trader_canary_account_total_usdt" not in metric_names
    # Required metrics are still present.
    assert "trader_canary_heartbeat_timestamp_seconds" in metric_names
    assert "trader_canary_ws_connected" in metric_names
    assert "trader_canary_daily_pnl_usdt" in metric_names
    assert "trader_canary_starting_balance_usdt" in metric_names


def test_render_textfile_metrics_includes_alert_total_per_alert_kind(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    sample = _make_sample()
    content = render_textfile_metrics(
        sample=sample,
        kind="testnet",
        run_id="r1",
        settings=settings,
        alert_counts={"ws_disconnected": 2, "signal_lag_exceeded_threshold": 5},
    )

    assert 'alert="ws_disconnected"' in content
    assert 'alert="signal_lag_exceeded_threshold"' in content
    assert "trader_canary_alert_total" in content
    # Counter values appear next to their label sets.
    alert_lines = [
        line for line in content.splitlines()
        if line.startswith("trader_canary_alert_total{")
    ]
    assert len(alert_lines) == 2
    assert any(line.endswith(" 2") for line in alert_lines)
    assert any(line.endswith(" 5") for line in alert_lines)


def test_render_textfile_metrics_ws_connected_zero_when_false(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    sample = _make_sample(ws_connected=False)
    content = render_textfile_metrics(
        sample=sample,
        kind="testnet",
        run_id="r1",
        settings=settings,
        alert_counts={},
    )

    # Locate the ws_connected gauge line.
    ws_line = next(
        line for line in content.splitlines()
        if line.startswith("trader_canary_ws_connected{")
    )
    assert ws_line.endswith(" 0")


def test_render_textfile_metrics_label_value_escaping(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    sample = _make_sample()
    content = render_textfile_metrics(
        sample=sample,
        kind='evil"kind',
        run_id="r1",
        settings=settings,
        alert_counts={},
    )
    # Backslash-escape both backslash and double-quote per Prometheus exposition.
    assert r'kind="evil\"kind"' in content


def test_write_textfile_atomic_is_replacing_not_appending(tmp_path: Path) -> None:
    target = tmp_path / "metrics.prom"
    write_textfile_atomic(target, "first\n")
    write_textfile_atomic(target, "second\n")
    assert target.read_text(encoding="utf-8") == "second\n"
    # The .tmp sibling must not linger.
    assert not (tmp_path / "metrics.prom.tmp").exists()


def test_write_textfile_atomic_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c.prom"
    write_textfile_atomic(nested, "x\n")
    assert nested.read_text(encoding="utf-8") == "x\n"


def test_prometheus_textfile_writer_path_is_kind_run_id(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    writer = PrometheusTextfileWriter(
        target_dir=tmp_path / "obs",
        run_id="20260520-120000Z-abcd1234",
        kind="testnet",
        settings=settings,
    )
    assert writer.path == tmp_path / "obs" / "testnet-20260520-120000Z-abcd1234.prom"


def test_prometheus_textfile_writer_record_alert_is_cumulative(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    writer = PrometheusTextfileWriter(
        target_dir=tmp_path / "obs",
        run_id="r1",
        kind="testnet",
        settings=settings,
    )
    writer.record_alert("ws_disconnected")
    writer.record_alert("ws_disconnected")
    writer.record_alert("kill_switch_fired")
    assert writer.alert_counts == {
        "ws_disconnected": 2,
        "kill_switch_fired": 1,
    }


def test_prometheus_textfile_writer_write_sample_emits_alert_counts(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    writer = PrometheusTextfileWriter(
        target_dir=tmp_path / "obs",
        run_id="r1",
        kind="testnet",
        settings=settings,
    )
    writer.record_alert("ws_disconnected")
    writer.write_sample(_make_sample())
    content = writer.path.read_text(encoding="utf-8")
    assert 'alert="ws_disconnected"' in content
    assert content.rstrip().endswith("trader_canary_info{kind=\"testnet\",run_id=\"r1\"} 1")


def test_prometheus_textfile_writer_cleanup_removes_file(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    writer = PrometheusTextfileWriter(
        target_dir=tmp_path / "obs",
        run_id="r1",
        kind="testnet",
        settings=settings,
    )
    writer.write_sample(_make_sample())
    assert writer.path.exists()
    writer.cleanup()
    assert not writer.path.exists()


def test_prometheus_textfile_writer_cleanup_is_idempotent(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    writer = PrometheusTextfileWriter(
        target_dir=tmp_path / "obs",
        run_id="r1",
        kind="testnet",
        settings=settings,
    )
    # Never written — cleanup must not raise.
    writer.cleanup()
    # Calling again is also a no-op.
    writer.cleanup()


def test_long_run_settings_observability_dir_defaults_to_none(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    assert settings.observability_textfile_dir is None


def test_long_run_settings_accepts_observability_dir(tmp_path: Path) -> None:
    settings = LongRunningTestnetSettings(
        output_root=tmp_path / "out",
        instrument_ids=("BTCUSDT.BINANCE",),
        starting_balance=10_000.0,
        observability_textfile_dir=tmp_path / "obs",
    )
    assert settings.observability_textfile_dir == tmp_path / "obs"


# ---------------------------------------------------------------------------
# Integration with run_long_running_testnet
# ---------------------------------------------------------------------------


_VALID_ENV = {
    "BINANCE_TESTNET_API_KEY": "K" * 40,
    "BINANCE_TESTNET_API_SECRET": "S" * 40,
}
_GIT_CLEAN = GitState(commit="a" * 40, dirty=False)


def _startup_settings(tmp_path: Path) -> StartupSettings:
    retros = tmp_path / "retros"
    retros.mkdir(parents=True, exist_ok=True)
    return StartupSettings(
        mode="testnet",
        kind="testnet",
        allow_real_credentials=True,
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        policy_position_pct_multiplier=0.1,
        retros_dir=retros,
        repo_root=tmp_path,
        operator="pytest",
    )


def _long_run_settings_with_obs(
    tmp_path: Path, obs_dir: Path | None
) -> LongRunningTestnetSettings:
    return LongRunningTestnetSettings(
        output_root=tmp_path / "data" / "testnet",
        instrument_ids=("BTCUSDT.BINANCE",),
        starting_balance=10_000.0,
        max_run_seconds=0.05,
        telemetry_poll_seconds=0.001,
        heartbeat_interval_seconds=30.0,
        emergency_fill_timeout_seconds=1.0,
        emergency_poll_interval_seconds=0.1,
        observability_textfile_dir=obs_dir,
    )


class _BlockingFakeTrader:
    def __init__(self) -> None:
        self.strategies: list[object] = []
        self.actors: list[object] = []


class _BlockingFakeNode:
    def __init__(self, node_config: Any) -> None:
        self.node_config = node_config
        self.trader = _BlockingFakeTrader()
        self.stop_called = False

    def add_data_client_factory(self, name: str, factory: type) -> None:
        return None

    def add_exec_client_factory(self, name: str, factory: type) -> None:
        return None

    def build(self) -> None:
        return None

    def run(self, raise_exception: bool = False) -> None:
        while not self.stop_called:
            time.sleep(0.001)

    def stop(self) -> None:
        self.stop_called = True

    def dispose(self) -> None:
        return None


def _frozen_clock(base: datetime, step_seconds: float = 1.0):
    state = {"t": base}

    def _now() -> datetime:
        current = state["t"]
        state["t"] = current + timedelta(seconds=step_seconds)
        return current

    return _now


def _retro_for_promotion(retros: Path) -> None:
    (retros / "2026-05-17-freqai-linear-v1-hold-paper-simulated.md").write_text(
        "\n".join(
            [
                "# Promotion review — freqai_linear_v1 / linear-mom-train20240105",
                "## 1. Source / model",
                "- source: `freqai_linear_v1`",
                "- model_version: `linear-mom-train20240105`",
                "## 2. Current vs target policy",
                "- current_stage: `paper_simulated`",
                "- target_stage: `paper_simulated`",
                "## 7. Conclusion",
                "- decision: **HOLD**",
                "- decision_allowed: **yes**",
            ]
        ),
        encoding="utf-8",
    )


class _SpyTextfileWriter(PrometheusTextfileWriter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.write_sample_calls = 0
        self.cleanup_calls = 0
        self.last_content: str | None = None

    def write_sample(self, sample: TestnetRuntimeTelemetry) -> None:
        super().write_sample(sample)
        self.write_sample_calls += 1
        try:
            self.last_content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self.last_content = None

    def cleanup(self) -> None:
        super().cleanup()
        self.cleanup_calls += 1


def test_run_long_running_testnet_invokes_textfile_writer(tmp_path: Path) -> None:
    settings = _startup_settings(tmp_path)
    _retro_for_promotion(settings.retros_dir)
    obs_dir = tmp_path / "obs"
    run_settings = _long_run_settings_with_obs(tmp_path, obs_dir=obs_dir)
    base = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    sample = TestnetRuntimeTelemetry(
        ts=base,
        daily_pnl=0.0,
        exchange_error_count=0,
        ws_reconnect_count=0,
        account_total_usdt=10_000.0,
        open_orders=0,
        open_positions=0,
        last_bar_ns=1_700_000_000_000_000_000,
        last_signal_ns=1_700_000_000_500_000_000,
        ws_connected=True,
    )
    spy = _SpyTextfileWriter(
        target_dir=obs_dir,
        run_id="20260520-120000Z-testfile",
        kind="testnet",
        settings=run_settings,
    )

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=_VALID_ENV,
        git_state=_GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        clock_ns=lambda: 1714521540123456789,
        telemetry_reader=lambda: sample,
        textfile_writer=spy,
        run_id="20260520-120000Z-testfile",
    )

    assert result.stop_reason == "max_duration"
    assert spy.write_sample_calls >= 1
    assert spy.cleanup_calls == 1
    # Cleanup removed the live file so node_exporter no longer exposes stale data.
    assert not spy.path.exists()
    # The last captured content carried the expected identity labels.
    assert spy.last_content is not None
    assert 'kind="testnet"' in spy.last_content
    assert 'run_id="20260520-120000Z-testfile"' in spy.last_content


def test_run_long_running_testnet_skips_export_when_obs_dir_is_none(
    tmp_path: Path,
) -> None:
    settings = _startup_settings(tmp_path)
    _retro_for_promotion(settings.retros_dir)
    run_settings = _long_run_settings_with_obs(tmp_path, obs_dir=None)
    base = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    sample = TestnetRuntimeTelemetry(
        ts=base,
        daily_pnl=0.0,
        exchange_error_count=0,
        ws_reconnect_count=0,
        account_total_usdt=10_000.0,
        open_orders=0,
        open_positions=0,
        last_bar_ns=1_700_000_000_000_000_000,
        last_signal_ns=1_700_000_000_500_000_000,
        ws_connected=True,
    )

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=_VALID_ENV,
        git_state=_GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        clock_ns=lambda: 1714521540123456789,
        telemetry_reader=lambda: sample,
        run_id="20260520-120000Z-noobs",
    )

    assert result.stop_reason == "max_duration"
    # No textfile dir means no .prom file anywhere under tmp_path.
    assert not list(tmp_path.rglob("*.prom"))


def test_run_long_running_testnet_records_alerts_in_textfile(tmp_path: Path) -> None:
    settings = _startup_settings(tmp_path)
    _retro_for_promotion(settings.retros_dir)
    obs_dir = tmp_path / "obs"
    run_settings = _long_run_settings_with_obs(tmp_path, obs_dir=obs_dir)
    base = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    # Reader returns a sample that trips ws_disconnected → ADR-008 §5.4 advisory alert.
    disconnected_sample = TestnetRuntimeTelemetry(
        ts=base,
        daily_pnl=0.0,
        exchange_error_count=0,
        ws_reconnect_count=0,
        account_total_usdt=10_000.0,
        open_orders=0,
        open_positions=0,
        last_bar_ns=1_700_000_000_000_000_000,
        last_signal_ns=1_700_000_000_500_000_000,
        ws_connected=False,
    )
    spy = _SpyTextfileWriter(
        target_dir=obs_dir,
        run_id="20260520-120000Z-alert",
        kind="testnet",
        settings=run_settings,
    )

    run_long_running_testnet(
        settings,
        run_settings,
        env=_VALID_ENV,
        git_state=_GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        clock_ns=lambda: 1714521540123456789,
        telemetry_reader=lambda: disconnected_sample,
        textfile_writer=spy,
        run_id="20260520-120000Z-alert",
    )

    # The disconnected sample fires ws_disconnected once on the True→False edge.
    assert spy.alert_counts.get("ws_disconnected") == 1
    assert spy.last_content is not None
    assert 'alert="ws_disconnected"' in spy.last_content


def test_observability_configs_wire_watchdog_history_and_alert_rules() -> None:
    prometheus = Path("infra/prometheus/prometheus.yml").read_text(encoding="utf-8")
    alert_rules = Path("infra/prometheus/alert_rules.yml").read_text(encoding="utf-8")
    promtail = Path("infra/promtail/promtail.yml").read_text(encoding="utf-8")
    compose = Path("infra/docker-compose.yml").read_text(encoding="utf-8")

    assert "/etc/prometheus/alert_rules.yml" in prometheus
    for alert_name in (
        "TraderCanaryHeartbeatStale",
        "TraderCanaryWsDisconnected",
        "TraderCanaryExchangeErrorBurst",
        "TraderCanaryOpenPositionWithoutFreshHeartbeat",
    ):
        assert alert_name in alert_rules

    assert "job_name: watchdog_history" in promtail
    assert "__path__: /data/watchdog/history.jsonl" in promtail
    assert "./watchdog:/data/watchdog:ro" in compose
    assert "./prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro" in compose
