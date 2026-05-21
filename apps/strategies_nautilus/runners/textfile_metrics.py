"""Prometheus textfile collector export for the testnet long-running runner.

The ADR-008 §6.6 testnet canary already writes ``heartbeat.jsonl``,
``alerts.log``, ``runtime.log``, ``run_manifest.json``, and parquet sidecars
under ``data/testnet/<run_id>/`` as the durable bundle evidence. This module
adds a *secondary* exporter that mirrors the latest monitor sample into a
single ``.prom`` file outside the bundle, so node_exporter's textfile
collector can scrape it and surface live metrics in Prometheus / Grafana.

Design constraints:

- Bundle integrity is untouched. ``.prom`` files live under a separate
  ``data/observability/textfile/`` root by default and are deleted on
  shutdown. Prometheus retains the historical series in its own TSDB.
- Writes are atomic (``write to .tmp, os.replace``) so node_exporter
  never reads a half-written file.
- All exceptions from the writer are swallowed by the caller — telemetry
  export must never crash the monitor loop or change the runner exit code.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.strategies_nautilus.runners.testnet_runner import (
        LongRunningTestnetSettings,
        TestnetRuntimeTelemetry,
    )


_METRIC_HELP: tuple[tuple[str, str, str], ...] = (
    (
        "trader_canary_heartbeat_timestamp_seconds",
        "gauge",
        "Wall-clock timestamp of the most recent monitor sample, seconds since UTC epoch.",
    ),
    (
        "trader_canary_ws_connected",
        "gauge",
        "Whether the runner's data+exec WS clients were both connected at the last sample (1) or not (0).",
    ),
    (
        "trader_canary_ws_reconnect_total",
        "counter",
        "Cumulative WS reconnect count observed by the runner since startup.",
    ),
    (
        "trader_canary_exchange_error_total",
        "counter",
        "Cumulative exchange error count observed by the runner since startup.",
    ),
    (
        "trader_canary_open_orders",
        "gauge",
        "Open order count at the last sample (omitted when the runner could not read it).",
    ),
    (
        "trader_canary_open_positions",
        "gauge",
        "Open position count at the last sample (omitted when the runner could not read it).",
    ),
    (
        "trader_canary_daily_pnl_usdt",
        "gauge",
        "Daily realized + unrealized PnL anchored at UTC day rollover, in USDT.",
    ),
    (
        "trader_canary_account_total_usdt",
        "gauge",
        "Total account equity in USDT at the last sample (omitted when unavailable).",
    ),
    (
        "trader_canary_last_bar_timestamp_seconds",
        "gauge",
        "Timestamp of the last bar observed by the strategy (omitted when unavailable).",
    ),
    (
        "trader_canary_last_signal_timestamp_seconds",
        "gauge",
        "Timestamp of the last signal popped by the polling source (omitted when unavailable).",
    ),
    (
        "trader_canary_starting_balance_usdt",
        "gauge",
        "Configured starting balance in USDT — the daily loss kill-switch reference.",
    ),
    (
        "trader_canary_daily_loss_limit_pct",
        "gauge",
        "Daily loss kill-switch limit as a fraction in (0,1].",
    ),
    (
        "trader_canary_alert_total",
        "counter",
        "Cumulative count of ADR-008 §5.2/§5.4 alerts emitted by the runner, by alert msg.",
    ),
    (
        "trader_canary_info",
        "gauge",
        "Constant 1 with run identity labels for joins.",
    ),
)


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_labels(labels: Mapping[str, str]) -> str:
    if not labels:
        return ""
    parts = [
        f'{key}="{_escape_label_value(value)}"' for key, value in sorted(labels.items())
    ]
    return "{" + ",".join(parts) + "}"


def _format_float(value: float) -> str:
    # Prometheus accepts decimal float, ``NaN``, ``+Inf``, ``-Inf``. We never
    # emit NaN/Inf here — callers omit a metric rather than emit garbage.
    return repr(float(value))


def render_textfile_metrics(
    *,
    sample: TestnetRuntimeTelemetry,
    kind: str,
    run_id: str,
    settings: LongRunningTestnetSettings,
    alert_counts: Mapping[str, int],
) -> str:
    """Render one Prometheus textfile collector payload for ``sample``.

    The output starts with ``# HELP`` / ``# TYPE`` lines for every metric we
    might emit (constant per process) followed by the actual sample values.
    Optional metrics (``open_orders`` etc.) are omitted when the underlying
    sample field is ``None``.
    """

    base_labels = {"kind": kind, "run_id": run_id}
    label_str = _format_labels(base_labels)
    lines: list[str] = []

    for name, mtype, help_text in _METRIC_HELP:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")

    ts_seconds = sample.ts.timestamp()
    lines.append(
        f"trader_canary_heartbeat_timestamp_seconds{label_str} {_format_float(ts_seconds)}"
    )
    lines.append(
        f"trader_canary_ws_connected{label_str} {1 if sample.ws_connected else 0}"
    )
    lines.append(
        f"trader_canary_ws_reconnect_total{label_str} {int(sample.ws_reconnect_count)}"
    )
    lines.append(
        f"trader_canary_exchange_error_total{label_str} {int(sample.exchange_error_count)}"
    )
    if sample.open_orders is not None:
        lines.append(
            f"trader_canary_open_orders{label_str} {int(sample.open_orders)}"
        )
    if sample.open_positions is not None:
        lines.append(
            f"trader_canary_open_positions{label_str} {int(sample.open_positions)}"
        )
    lines.append(
        f"trader_canary_daily_pnl_usdt{label_str} {_format_float(sample.daily_pnl)}"
    )
    if sample.account_total_usdt is not None:
        lines.append(
            f"trader_canary_account_total_usdt{label_str} {_format_float(sample.account_total_usdt)}"
        )
    if sample.last_bar_ns is not None:
        lines.append(
            f"trader_canary_last_bar_timestamp_seconds{label_str} {_format_float(sample.last_bar_ns / 1_000_000_000)}"
        )
    if sample.last_signal_ns is not None:
        lines.append(
            f"trader_canary_last_signal_timestamp_seconds{label_str} {_format_float(sample.last_signal_ns / 1_000_000_000)}"
        )

    lines.append(
        f"trader_canary_starting_balance_usdt{label_str} {_format_float(settings.starting_balance)}"
    )
    lines.append(
        f"trader_canary_daily_loss_limit_pct{label_str} {_format_float(settings.daily_loss_limit_pct)}"
    )

    for alert_kind, count in sorted(alert_counts.items()):
        alert_labels = {**base_labels, "alert": alert_kind}
        lines.append(
            f"trader_canary_alert_total{_format_labels(alert_labels)} {int(count)}"
        )

    lines.append(f"trader_canary_info{label_str} 1")
    return "\n".join(lines) + "\n"


def write_textfile_atomic(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically via ``.tmp`` + ``os.replace``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class PrometheusTextfileWriter:
    """Stateful writer used by the long-running testnet runner monitor loop.

    Holds the cumulative alert counter and the target ``.prom`` path. Methods
    are thread-safe via an internal lock so the monitor thread and the
    shutdown path don't race on the same file.
    """

    target_dir: Path
    run_id: str
    kind: str
    settings: LongRunningTestnetSettings
    _lock: threading.Lock = None  # type: ignore[assignment]
    alert_counts: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self.alert_counts = {}

    @property
    def path(self) -> Path:
        return self.target_dir / f"{self.kind}-{self.run_id}.prom"

    def record_alert(self, alert_msg: str) -> None:
        with self._lock:
            self.alert_counts[alert_msg] = self.alert_counts.get(alert_msg, 0) + 1

    def write_sample(self, sample: TestnetRuntimeTelemetry) -> None:
        with self._lock:
            content = render_textfile_metrics(
                sample=sample,
                kind=self.kind,
                run_id=self.run_id,
                settings=self.settings,
                alert_counts=self.alert_counts,
            )
            write_textfile_atomic(self.path, content)

    def cleanup(self) -> None:
        """Remove the live ``.prom`` file so node_exporter stops exposing it.

        Idempotent. Errors are swallowed — cleanup runs in the shutdown path
        and must never raise.
        """

        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


__all__ = [
    "PrometheusTextfileWriter",
    "render_textfile_metrics",
    "write_textfile_atomic",
]
