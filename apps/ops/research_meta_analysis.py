"""Program-level meta-analysis of the alpha research program (ADR-014 §5).

This is an evaluation artifact, not a trading identity: it writes no
``SignalEvent``, creates no source/model, mutates no ``SourcePolicy``, and its
price data covers only the already-opened evaluation windows (development
2020-01-01..2022-12-31, confirmation 2023-01-01..2025-12-31). The sealed
2026-09..2027-01 future blind is out of range by construction.

Subcommands:

- ``fetch-closes``: one-shot download of Binance Vision official monthly ``1d``
  spot kline archives for BTCUSDT (2020-01..2025-12), CHECKSUM-verified, into a
  single ``date,close`` CSV plus a SHA256 manifest under ``data/meta/``.
- ``build-report``: computes, from the committed results JSONs and the daily
  closes: buy-and-hold benchmarks per window, per-survivor capture ratios and
  breadth-vs-benchmark binomial p-values, and a two-stage random-timing
  Monte Carlo null that yields the expected number of lucky two-stage
  survivors given the family registry's evaluated-identity count.

The Monte Carlo null deliberately applies the *historical* (v48-era) gate set,
because the question is how often random timing passes the gates the actual
candidates faced. Gates v2 (ADR-014 §4) are stricter by design.
"""

from __future__ import annotations

import argparse
import glob as globmod
import hashlib
import io
import json
import math
import re
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCHEMA_VERSION = "research.meta_analysis.v1"
TRADE_SIZE_BTC = 0.001
DEV_WINDOW = ("2020-01-01", "2022-12-31")
CONF_WINDOW = ("2023-01-01", "2025-12-31")
# Historical (v48-era) gate set — the null must face what the candidates faced.
HISTORICAL_GATES = {
    "base_net_pnl_gt": 0.0,
    "stress_net_pnl_gt": 0.0,
    "positive_calendar_years_at_least": 2,
    "positive_calendar_months_at_least": 18,
    "closed_positions_at_least": 30,
    "leave_best_position_base_net_pnl_gt": 0.0,
}
COSTS_BPS = {"base": 12.0, "stress": 15.0}  # fee + slippage, per fill
BINANCE_VISION_BASE = "https://data.binance.vision/data/spot/monthly/klines"
DEFAULT_CLOSES_RELPATH = Path("data/meta/btcusdt-1d-closes-2020-2025.csv")
REGISTRY_RELPATH = Path("docs/progress/research-mechanism-family-registry.json")
REPORT_JSON_RELPATH = Path("docs/progress/research-program-meta-analysis-v1.json")
REPORT_MD_RELPATH = Path("docs/progress/research-program-meta-analysis-v1.md")

SURVIVOR_RESULT_GLOBS = (
    "docs/progress/phase-2-research-v*-confirmation-results.json",
    "docs/progress/phase-2-research-protocol-v*-confirmation-results.json",
)


# ---------------------------------------------------------------------------
# fetch-closes
# ---------------------------------------------------------------------------


def _month_range(start: str, end: str) -> list[str]:
    months = []
    cursor = pd.Period(start, freq="M")
    last = pd.Period(end, freq="M")
    while cursor <= last:
        months.append(str(cursor))
        cursor += 1
    return months


def _fetch_url(url: str, timeout: float = 60.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "trader-meta-analysis/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def _parse_checksum_file(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="replace").strip()
    match = re.match(r"^([0-9a-fA-F]{64})\b", text)
    if not match:
        raise ValueError(f"unparseable CHECKSUM payload: {text[:80]!r}")
    return match.group(1).lower()


def _closes_from_kline_zip(payload: bytes) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"expected one member in kline zip, got {names}")
        with archive.open(names[0]) as handle:
            for raw_line in io.TextIOWrapper(handle, encoding="utf-8"):
                line = raw_line.strip()
                if not line or line.startswith("open_time"):
                    continue
                parts = line.split(",")
                open_time = int(parts[0])
                # Binance Vision switched from ms to microsecond timestamps in 2025.
                unit = "us" if open_time > 10**14 else "ms"
                stamp = pd.Timestamp(open_time, unit=unit, tz="UTC")
                rows.append((stamp.date().isoformat(), float(parts[4])))
    return rows


def fetch_closes(
    out_csv: Path,
    *,
    symbol: str = "BTCUSDT",
    start_month: str = "2020-01",
    end_month: str = "2025-12",
    base_url: str = BINANCE_VISION_BASE,
) -> dict[str, Any]:
    """Download monthly 1d kline ZIPs once each, CHECKSUM-verified, into one CSV."""
    manifest_files = []
    all_rows: list[tuple[str, float]] = []
    for month in _month_range(start_month, end_month):
        name = f"{symbol}-1d-{month}.zip"
        url = f"{base_url}/{symbol}/1d/{name}"
        payload = _fetch_url(url)
        digest = hashlib.sha256(payload).hexdigest()
        expected = _parse_checksum_file(_fetch_url(url + ".CHECKSUM"))
        if digest != expected:
            raise ValueError(f"checksum mismatch for {name}: got {digest}, expected {expected}")
        rows = _closes_from_kline_zip(payload)
        if not rows:
            raise ValueError(f"no rows in {name}")
        all_rows.extend(rows)
        manifest_files.append({"file": name, "sha256": digest, "rows": len(rows)})
    frame = pd.DataFrame(all_rows, columns=["date", "close"]).sort_values("date")
    if frame["date"].duplicated().any():
        raise ValueError("duplicate dates across monthly archives")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_csv, index=False)
    csv_sha = hashlib.sha256(out_csv.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "research.meta_analysis.closes_manifest.v1",
        "symbol": symbol,
        "source": base_url,
        "months": [start_month, end_month],
        "row_count": int(len(frame)),
        "csv_path": out_csv.as_posix(),
        "csv_sha256": csv_sha,
        "files": manifest_files,
    }
    manifest_path = out_csv.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


# ---------------------------------------------------------------------------
# benchmark + null model core (offline, unit-testable)
# ---------------------------------------------------------------------------


def load_closes(path: Path) -> pd.Series:
    frame = pd.read_csv(path)
    if list(frame.columns) != ["date", "close"]:
        raise ValueError(f"expected date,close columns in {path}")
    index = pd.to_datetime(frame["date"], utc=True)
    series = pd.Series(frame["close"].to_numpy(dtype=float), index=index, name="close")
    if not series.index.is_monotonic_increasing:
        raise ValueError("closes must be date-sorted")
    gaps = pd.Series(series.index).diff().dropna().dt.days
    if (gaps != 1).any():
        raise ValueError("daily close series has calendar gaps")
    return series


def window(series: pd.Series, start: str, end: str) -> pd.Series:
    sliced = series.loc[str(start) : str(end)]
    if sliced.empty:
        raise ValueError(f"window {start}..{end} not covered by closes")
    return sliced


def buy_and_hold_stats(closes: pd.Series, trade_size: float = TRADE_SIZE_BTC) -> dict[str, Any]:
    pnl = float((closes.iloc[-1] - closes.iloc[0]) * trade_size)
    # month attribution via close-to-close daily PnL of a continuous hold
    daily_pnl = closes.diff() * trade_size
    month_index = closes.index.tz_localize(None).to_period("M")
    monthly_pnl = daily_pnl.groupby(month_index).sum()
    yearly_pnl = daily_pnl.groupby(closes.index.year).sum()
    return {
        "pnl": pnl,
        "months_total": int(monthly_pnl.shape[0]),
        "months_positive": int((monthly_pnl > 0).sum()),
        "years_positive": int((yearly_pnl > 0).sum()),
        "first_close": float(closes.iloc[0]),
        "last_close": float(closes.iloc[-1]),
    }


@dataclass
class NullParams:
    n_trials: int = 5000
    seed: int = 20260827
    fraction_low: float = 0.2
    fraction_high: float = 0.8
    hold_low_days: float = 2.0
    hold_high_days: float = 30.0


def _simulate_states(
    rng: np.random.Generator,
    n_days: int,
    p_on: np.ndarray,
    p_off: np.ndarray,
    initial: np.ndarray,
) -> np.ndarray:
    n_trials = p_on.shape[0]
    states = np.empty((n_trials, n_days), dtype=bool)
    current = initial.copy()
    uniforms = rng.random((n_days, n_trials))
    for day in range(n_days):
        u = uniforms[day]
        turn_on = ~current & (u < p_on)
        stay_on = current & (u >= p_off)
        current = turn_on | stay_on
        states[:, day] = current
    return states


def _window_gate_metrics(
    closes: pd.Series,
    states: np.ndarray,
    trade_size: float,
) -> dict[str, np.ndarray]:
    """Vectorized long/flat cash replay over one window for all trials."""
    prices = closes.to_numpy(dtype=float)
    n_trials, n_days = states.shape
    if n_days != len(prices):
        raise ValueError("state matrix does not match window length")
    price_diff = np.diff(prices, prepend=prices[0])
    held = np.concatenate([np.zeros((n_trials, 1), dtype=bool), states[:, :-1]], axis=1)
    gross_daily = held * price_diff[None, :] * trade_size

    prev = np.concatenate([np.zeros((n_trials, 1), dtype=bool), states[:, :-1]], axis=1)
    entries = states & ~prev
    exits = ~states & prev
    # force close at window end so every entry has an exit
    final_open = states[:, -1]
    fill_notional = (entries | exits) * prices[None, :] * trade_size
    fill_notional[:, -1] += final_open * prices[-1] * trade_size
    cost = {name: fill_notional.sum(axis=1) * (bps / 1e4) for name, bps in COSTS_BPS.items()}
    gross_total = gross_daily.sum(axis=1)
    base_total = gross_total - cost["base"]
    stress_total = gross_total - cost["stress"]

    month_periods = closes.index.tz_localize(None).to_period("M")
    _, month_starts = np.unique(month_periods.asi8, return_index=True)
    monthly = np.add.reduceat(gross_daily, month_starts, axis=1)
    base_fee_daily = (entries | exits) * prices[None, :] * trade_size * (COSTS_BPS["base"] / 1e4)
    base_fee_daily[:, -1] += final_open * prices[-1] * trade_size * (COSTS_BPS["base"] / 1e4)
    monthly_base = monthly - np.add.reduceat(base_fee_daily, month_starts, axis=1)
    months_positive = (monthly_base > 0).sum(axis=1)

    years = closes.index.year.to_numpy()
    _, year_starts = np.unique(years, return_index=True)
    yearly_base = np.add.reduceat(gross_daily - base_fee_daily, year_starts, axis=1)
    years_positive = (yearly_base > 0).sum(axis=1)

    positions = entries.sum(axis=1)

    # per-position base PnL for the leave-best gate (loop over trials; light)
    leave_best = np.empty(n_trials, dtype=float)
    for trial in range(n_trials):
        entry_idx = np.flatnonzero(entries[trial])
        if entry_idx.size == 0:
            leave_best[trial] = 0.0
            continue
        exit_idx = np.flatnonzero(exits[trial])
        if final_open[trial]:
            exit_idx = np.append(exit_idx, n_days - 1)
        best = -np.inf
        for e_i, x_i in zip(entry_idx, exit_idx, strict=True):
            gross_pos = trade_size * (prices[x_i] - prices[e_i])
            fee_pos = trade_size * (prices[x_i] + prices[e_i]) * (COSTS_BPS["base"] / 1e4)
            best = max(best, gross_pos - fee_pos)
        leave_best[trial] = base_total[trial] - best
    return {
        "base": base_total,
        "stress": stress_total,
        "months_positive": months_positive,
        "years_positive": years_positive,
        "positions": positions,
        "leave_best": leave_best,
        "months_total": np.full(n_trials, monthly.shape[1]),
    }


def _passes_gates(metrics: dict[str, np.ndarray]) -> np.ndarray:
    gates = HISTORICAL_GATES
    return (
        (metrics["base"] > gates["base_net_pnl_gt"])
        & (metrics["stress"] > gates["stress_net_pnl_gt"])
        & (metrics["years_positive"] >= gates["positive_calendar_years_at_least"])
        & (metrics["months_positive"] >= gates["positive_calendar_months_at_least"])
        & (metrics["positions"] >= gates["closed_positions_at_least"])
        & (metrics["leave_best"] > gates["leave_best_position_base_net_pnl_gt"])
    )


def run_random_timing_null(
    dev_closes: pd.Series,
    conf_closes: pd.Series,
    params: NullParams,
    trade_size: float = TRADE_SIZE_BTC,
) -> dict[str, Any]:
    rng = np.random.default_rng(params.seed)
    n = params.n_trials
    fraction = rng.uniform(params.fraction_low, params.fraction_high, size=n)
    hold = np.exp(
        rng.uniform(math.log(params.hold_low_days), math.log(params.hold_high_days), size=n)
    )
    p_off = np.clip(1.0 / hold, 1e-6, 1.0)
    p_on = np.clip(fraction * p_off / np.maximum(1.0 - fraction, 1e-9), 1e-6, 1.0)
    initial = rng.random(n) < fraction

    dev_states = _simulate_states(rng, len(dev_closes), p_on, p_off, initial)
    dev_metrics = _window_gate_metrics(dev_closes, dev_states, trade_size)
    dev_pass = _passes_gates(dev_metrics)

    conf_initial = dev_states[:, -1]
    conf_states = _simulate_states(rng, len(conf_closes), p_on, p_off, conf_initial)
    conf_metrics = _window_gate_metrics(conf_closes, conf_states, trade_size)
    conf_pass = _passes_gates(conf_metrics)

    both = dev_pass & conf_pass
    return {
        "n_trials": n,
        "seed": params.seed,
        "p_dev_pass": float(dev_pass.mean()),
        "p_conf_pass_given_dev": float(conf_pass[dev_pass].mean()) if dev_pass.any() else 0.0,
        "p_two_stage_pass": float(both.mean()),
        "dev_base_pnl_quantiles": {
            "q50": float(np.quantile(dev_metrics["base"], 0.5)),
            "q90": float(np.quantile(dev_metrics["base"], 0.9)),
        },
        "conf_base_pnl_mean_given_two_stage": (
            float(conf_metrics["base"][both].mean()) if both.any() else None
        ),
        "params": {
            "fraction_range": [params.fraction_low, params.fraction_high],
            "hold_days_range": [params.hold_low_days, params.hold_high_days],
            "gates": HISTORICAL_GATES,
            "costs_bps_per_fill": COSTS_BPS,
        },
    }


def evaluate_long_flat_states(
    closes_window: pd.Series,
    states: np.ndarray,
    trade_size: float = TRADE_SIZE_BTC,
) -> dict[str, Any]:
    """Gate metrics for one long/flat daily state series (shared protocol harness)."""
    metrics = _window_gate_metrics(closes_window, states[None, :].astype(bool), trade_size)
    held = np.concatenate([[False], states[:-1].astype(bool)])
    positions = int(metrics["positions"][0])
    return {
        "base_net_pnl": float(metrics["base"][0]),
        "stress_net_pnl": float(metrics["stress"][0]),
        "positive_months": int(metrics["months_positive"][0]),
        "months_total": int(metrics["months_total"][0]),
        "positive_years": int(metrics["years_positive"][0]),
        "closed_positions": positions,
        "leave_best_base_net_pnl": float(metrics["leave_best"][0]),
        "time_in_market_fraction": float(held.mean()),
        "mean_holding_days": float(held.sum() / positions) if positions else 0.0,
    }


def matched_random_timing_p_value(
    closes_window: pd.Series,
    *,
    base_net_pnl: float,
    time_in_market_fraction: float,
    mean_holding_days: float,
    trade_size: float = TRADE_SIZE_BTC,
    n_trials: int = 20000,
    seed: int = 20260827,
) -> float:
    """Exposure/cadence-matched random-timing p-value for a candidate's base PnL.

    Null: Markov long/flat daily timing with exposure fraction ~ U(f-0.15, f+0.15)
    clipped to (0.02, 0.98) and mean hold ~ logU(max(1.5, h/2), 2h), same window
    and base costs. p = (1 + #{null base >= candidate base}) / (n_trials + 1).
    """
    rng = np.random.default_rng(seed)
    hold_center = max(mean_holding_days, 1.5)
    frac_low = min(max(time_in_market_fraction - 0.15, 0.02), 0.9)
    frac_high = max(min(time_in_market_fraction + 0.15, 0.98), frac_low + 0.01)
    hold_low = max(1.5, hold_center / 2.0)
    hold_high = max(hold_low + 0.1, hold_center * 2.0)
    fraction = rng.uniform(frac_low, frac_high, size=n_trials)
    hold = np.exp(rng.uniform(math.log(hold_low), math.log(hold_high), size=n_trials))
    p_off = np.clip(1.0 / hold, 1e-6, 1.0)
    p_on = np.clip(fraction * p_off / np.maximum(1.0 - fraction, 1e-9), 1e-6, 1.0)
    initial = rng.random(n_trials) < fraction
    states = _simulate_states(rng, len(closes_window), p_on, p_off, initial)
    metrics = _window_gate_metrics(closes_window, states, trade_size)
    exceed = int((metrics["base"] >= base_net_pnl).sum())
    return (1 + exceed) / (n_trials + 1)


def _binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), exact summation."""
    if p <= 0.0:
        return 0.0 if k > 0 else 1.0
    if p >= 1.0:
        return 1.0
    total = 0.0
    log_p = math.log(p)
    log_q = math.log1p(-p)
    for i in range(k, n + 1):
        log_term = (
            math.lgamma(n + 1)
            - math.lgamma(i + 1)
            - math.lgamma(n - i + 1)
            + i * log_p
            + (n - i) * log_q
        )
        total += math.exp(log_term)
    return min(1.0, total)


# ---------------------------------------------------------------------------
# survivor stats from committed confirmation results
# ---------------------------------------------------------------------------


def _extract_candidate_stats(blob: dict[str, Any]) -> dict[str, Any] | None:
    keys = ("base_net_pnl", "positive_months", "closed_positions")
    if all(key in blob for key in keys):
        return {
            "source": blob.get("source"),
            "model_version": blob.get("model_version"),
            "base_net_pnl": float(blob["base_net_pnl"]),
            "stress_net_pnl": (
                float(blob["stress_net_pnl"]) if blob.get("stress_net_pnl") is not None else None
            ),
            "positive_months": int(blob["positive_months"]),
            "closed_positions": int(blob["closed_positions"]),
            "leave_best_base_net_pnl": (
                float(blob["leave_best_base_net_pnl"])
                if blob.get("leave_best_base_net_pnl") is not None
                else None
            ),
        }
    return None


def collect_survivor_stats(repo_root: Path, survivor_models: set[str]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for pattern in SURVIVOR_RESULT_GLOBS:
        for path in sorted(globmod.glob(str(repo_root / pattern))):
            try:
                payload = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            blobs: list[dict[str, Any]] = []
            if isinstance(payload, dict):
                blobs.append(payload)
                candidate = payload.get("candidate")
                if isinstance(candidate, dict):
                    blobs.append(candidate)
                candidates = payload.get("candidates")
                if isinstance(candidates, dict):
                    blobs.extend(v for v in candidates.values() if isinstance(v, dict))
            for blob in blobs:
                stats = _extract_candidate_stats(blob)
                if stats and stats["model_version"] in survivor_models:
                    stats["evidence_path"] = Path(path).as_posix()
                    rows[stats["model_version"]] = stats
    return [rows[model] for model in sorted(rows)]


# ---------------------------------------------------------------------------
# report assembly
# ---------------------------------------------------------------------------


def build_report(
    repo_root: Path,
    closes_path: Path,
    *,
    null_params: NullParams,
) -> dict[str, Any]:
    registry = json.loads((repo_root / REGISTRY_RELPATH).read_text(encoding="utf-8"))
    totals = registry["totals"]
    survivor_models = {
        cand["model_version"]
        for proto in registry["protocols"]
        for cand in proto["candidates"]
        if cand["outcome"] == "confirmation_passed_paper_shadow"
    }

    closes = load_closes(closes_path)
    dev = window(closes, *DEV_WINDOW)
    conf = window(closes, *CONF_WINDOW)
    bh_dev = buy_and_hold_stats(dev)
    bh_conf = buy_and_hold_stats(conf)

    survivors = collect_survivor_stats(repo_root, survivor_models)
    bh_month_fraction = bh_conf["months_positive"] / bh_conf["months_total"]
    for row in survivors:
        row["capture_ratio_vs_bh_conf"] = (
            row["base_net_pnl"] / bh_conf["pnl"] if bh_conf["pnl"] else None
        )
        row["months_breadth_binom_p_vs_bh"] = _binom_sf(
            row["positive_months"], 36, bh_month_fraction
        )

    null = run_random_timing_null(dev, conf, null_params)
    n_evaluated = int(totals["unique_identities_pnl_opened"])
    observed_survivors = int(totals["survivors_paper_shadow"])
    expected_lucky = n_evaluated * null["p_two_stage_pass"]
    p_observed_or_more = _binom_sf(observed_survivors, n_evaluated, null["p_two_stage_pass"])

    return {
        "schema_version": SCHEMA_VERSION,
        "adr": "docs/decisions/014-research-program-v2.md",
        "boundaries": {
            "writes_signal_events": False,
            "mutates_source_policy": False,
            "opens_future_blind": False,
            "touches_live_path": False,
            "windows": {"development": list(DEV_WINDOW), "confirmation": list(CONF_WINDOW)},
        },
        "inputs": {
            "closes_csv": (
                closes_path.resolve().relative_to(repo_root.resolve()).as_posix()
                if closes_path.resolve().is_relative_to(repo_root.resolve())
                else closes_path.as_posix()
            ),
            "closes_sha256": hashlib.sha256(closes_path.read_bytes()).hexdigest(),
            "closes_rows": int(len(closes)),
            "registry": REGISTRY_RELPATH.as_posix(),
            "registry_as_of": registry["as_of"],
        },
        "buy_and_hold": {
            "trade_size_btc": TRADE_SIZE_BTC,
            "development": bh_dev,
            "confirmation": bh_conf,
        },
        "survivors": survivors,
        "random_timing_null": null,
        "program_multiplicity": {
            "identities_pnl_opened": n_evaluated,
            "observed_two_stage_survivors": observed_survivors,
            "expected_lucky_two_stage_survivors": expected_lucky,
            "p_observed_or_more_by_luck": p_observed_or_more,
            "note": (
                "Null assumes independent random long/flat timing per identity on "
                "BTCUSDT with survivor-like exposure and holding cadence, evaluated "
                "under the historical two-stage gate set. Family correlation between "
                "identities makes the effective trial count lower and the null "
                "conservative in that direction; selective advancement of the best "
                "development sibling makes it anti-conservative. Read as calibration, "
                "not as a verdict."
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    bh_dev = report["buy_and_hold"]["development"]
    bh_conf = report["buy_and_hold"]["confirmation"]
    null = report["random_timing_null"]
    multi = report["program_multiplicity"]
    lines = [
        "# Research Program Meta-Analysis v1 (ADR-014 §5)",
        "",
        f"- **Schema**: `{report['schema_version']}`",
        f"- **Registry**: `{report['inputs']['registry']}` (as of {report['inputs']['registry_as_of']})",
        f"- **Closes**: `{report['inputs']['closes_csv']}` "
        f"(rows={report['inputs']['closes_rows']}, sha256={report['inputs']['closes_sha256'][:16]}…)",
        f"- **Windows**: development {DEV_WINDOW[0]}..{DEV_WINDOW[1]}, "
        f"confirmation {CONF_WINDOW[0]}..{CONF_WINDOW[1]}; future blind untouched.",
        "",
        "## 1. Buy-and-hold benchmark (trade size 0.001 BTC)",
        "",
        "| Window | B&H PnL (USDT) | Positive months | Positive years |",
        "|---|---|---|---|",
        f"| Development 2020-2022 | {bh_dev['pnl']:+.2f} | "
        f"{bh_dev['months_positive']}/{bh_dev['months_total']} | {bh_dev['years_positive']}/3 |",
        f"| Confirmation 2023-2025 | {bh_conf['pnl']:+.2f} | "
        f"{bh_conf['months_positive']}/{bh_conf['months_total']} | {bh_conf['years_positive']}/3 |",
        "",
        "The historical `>=18/36 positive months` gate should be read against the",
        "B&H month-positive rate above: a long/flat rule can meet it while doing",
        "nothing beyond holding beta part-time (warning W1/W4).",
        "",
        "## 2. Survivors vs benchmark (confirmation window)",
        "",
        "| Model | Base PnL | Capture vs B&H | Months+ | Breadth p vs B&H | Positions |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["survivors"]:
        capture = row["capture_ratio_vs_bh_conf"]
        lines.append(
            f"| `{row['model_version']}` | {row['base_net_pnl']:+.2f} | "
            f"{capture:.2%} | {row['positive_months']}/36 | "
            f"{row['months_breadth_binom_p_vs_bh']:.3f} | {row['closed_positions']} |"
        )
    missing = multi["observed_two_stage_survivors"] - len(report["survivors"])
    if missing > 0:
        lines.append("")
        lines.append(
            f"({missing} survivor result file(s) were not machine-readable for PnL "
            "fields; their gate outcomes are recorded in the registry.)"
        )
    lines += [
        "",
        "## 3. Two-stage random-timing null",
        "",
        f"- Trials: {null['n_trials']} (seed {null['seed']}); exposure fraction "
        f"U{null['params']['fraction_range']}, mean hold logU{null['params']['hold_days_range']} days;",
        f"  costs per fill (bps): {null['params']['costs_bps_per_fill']}; historical gate set.",
        f"- P(pass development gates by luck) = **{null['p_dev_pass']:.3%}**",
        f"- P(pass confirmation | passed development) = **{null['p_conf_pass_given_dev']:.3%}**",
        f"- P(pass both stages by luck) = **{null['p_two_stage_pass']:.3%}**",
        "",
        "## 4. Program-level multiplicity",
        "",
        f"- Identities with PnL opened (registry): **{multi['identities_pnl_opened']}**",
        f"- Observed two-stage survivors: **{multi['observed_two_stage_survivors']}**",
        f"- Expected lucky two-stage survivors: **{multi['expected_lucky_two_stage_survivors']:.2f}**",
        f"- P(observed ≥ {multi['observed_two_stage_survivors']} by luck alone): "
        f"**{multi['p_observed_or_more_by_luck']:.4f}**",
        "",
        f"> {multi['note']}",
        "",
        "## 5. Boundaries",
        "",
        "- No `SignalEvent` written, no `SourcePolicy` change, no live-path impact.",
        "- The 2026-09..2027-01 future blind was not read.",
        "- This report informs the ADR-014 §6 portfolio review; it demotes nothing by itself.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("repo root with pyproject.toml not found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch-closes", help="one-shot Binance Vision daily-close download")
    fetch.add_argument("--out", type=Path, default=None)
    fetch.add_argument("--start-month", default="2020-01")
    fetch.add_argument("--end-month", default="2025-12")

    build = sub.add_parser("build-report", help="build the meta-analysis report")
    build.add_argument("--closes", type=Path, default=None)
    build.add_argument("--out-json", type=Path, default=None)
    build.add_argument("--out-md", type=Path, default=None)
    build.add_argument("--trials", type=int, default=NullParams.n_trials)
    build.add_argument("--seed", type=int, default=NullParams.seed)

    args = parser.parse_args(argv)
    repo_root = _find_repo_root()

    if args.command == "fetch-closes":
        out = args.out or (repo_root / DEFAULT_CLOSES_RELPATH)
        manifest = fetch_closes(out, start_month=args.start_month, end_month=args.end_month)
        print(json.dumps({k: manifest[k] for k in ("row_count", "csv_sha256")}, indent=2))
        return 0

    closes_path = args.closes or (repo_root / DEFAULT_CLOSES_RELPATH)
    report = build_report(
        repo_root,
        closes_path,
        null_params=NullParams(n_trials=args.trials, seed=args.seed),
    )
    out_json = args.out_json or (repo_root / REPORT_JSON_RELPATH)
    out_md = args.out_md or (repo_root / REPORT_MD_RELPATH)
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json.as_posix()} and {out_md.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
