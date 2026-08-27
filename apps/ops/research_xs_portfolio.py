"""Contract-parameterized harness for cross-sectional long/short protocols (ADR-014 §6.4).

Pipeline for dollar-neutral weekly-rebalanced rank portfolios over Binance
spot daily closes: ``fetch-dev`` → ``qualify`` → ``develop`` → ``confirm``.
Everything evaluative (pool, universe rule, mechanisms, lookbacks, leg
counts, notionals, costs, windows, gates, permutation null, delisting rule)
comes from the bound contract module (``apps.ops.research_protocol_v52``,
...), and every stage output records that contract's ``contract_sha256()``.

Replay conventions (frozen by the contracts that bind this harness):

- fixed leg notionals (no compounding): a leg's daily PnL is
  ``sign * notional * daily_simple_return``;
- rankings use closes up to and including the rebalance close; positions are
  carried from strictly after the rebalance day until the next rebalance;
- fills cost ``notional * (fee+slippage)`` per entering and per exiting leg;
  a leg persisting on the same side pays nothing;
- a symbol whose archive ends inside a window is force-closed at its last
  available close and excluded from rankings thereafter (delisting rule);
- if the eligible universe falls below the contract minimum, the book goes
  flat until it recovers (fail-safe).

The permutation null replaces the ranking with an independent uniform random
permutation at every rebalance, keeping calendar, universe evolution, leg
counts, notionals, and costs identical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

from apps.ops.research_meta_analysis import (
    _closes_from_kline_zip,
    _fetch_url,
    _month_range,
    _parse_checksum_file,
)

BINANCE_SPOT_KLINES = "https://data.binance.vision/data/spot/monthly/klines"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _protocol_tag(contract: ModuleType) -> str:
    match = re.match(r"^research\.protocol\.(v\d+)\.", contract.SCHEMA_VERSION)
    if not match:
        raise ValueError(f"cannot derive protocol tag from {contract.SCHEMA_VERSION!r}")
    return match.group(1)


def _output_path(repo_root: Path, contract: ModuleType, kind: str) -> Path:
    tag = _protocol_tag(contract)
    return repo_root / "docs" / "progress" / f"phase-2-research-{tag}-{kind}.json"


def _closes_dir(repo_root: Path, contract: ModuleType) -> Path:
    return repo_root / contract.CLOSES_SOURCE["closes_dir"]


# ---------------------------------------------------------------------------
# fetch + load
# ---------------------------------------------------------------------------


def fetch_symbol_closes(
    out_csv: Path,
    *,
    symbol: str,
    months: list[str],
    allow_partial: bool,
) -> dict[str, Any]:
    """One CHECKSUM-verified GET per monthly 1d kline archive into a date,close CSV.

    ``allow_partial=True`` (confirmation only) stops cleanly at the first
    missing month — the mechanical delisting rule; development requires every
    month and re-raises instead.
    """
    rows: list[tuple[str, float]] = []
    fetched: list[str] = []
    complete = True
    for month in months:
        name = f"{symbol}-1d-{month}.zip"
        url = f"{BINANCE_SPOT_KLINES}/{symbol}/1d/{name}"
        try:
            payload = _fetch_url(url)
        except Exception:
            if allow_partial:
                complete = False
                break
            raise
        expected = _parse_checksum_file(_fetch_url(url + ".CHECKSUM"))
        digest = hashlib.sha256(payload).hexdigest()
        if digest != expected:
            raise ValueError(f"checksum mismatch for {name}")
        rows.extend(_closes_from_kline_zip(payload))
        fetched.append(month)
    frame = pd.DataFrame(rows, columns=["date", "close"]).sort_values("date")
    if frame["date"].duplicated().any():
        raise ValueError(f"{symbol}: duplicate dates across monthly archives")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_csv, index=False)
    return {
        "symbol": symbol,
        "path": out_csv.name,
        "rows": int(len(frame)),
        "months_fetched": fetched,
        "complete": complete,
        "sha256": _sha256_file(out_csv),
    }


def run_fetch_dev(repo_root: Path, contract: ModuleType) -> dict[str, Any]:
    months = _month_range(*contract.CLOSES_SOURCE["development_months"])
    out_dir = _closes_dir(repo_root, contract)
    results = []
    for symbol in contract.SYMBOL_POOL:
        out_csv = out_dir / f"{symbol}-dev.csv"
        if out_csv.exists():
            results.append({"symbol": symbol, "path": out_csv.name, "cached": True})
            continue
        try:
            results.append(
                fetch_symbol_closes(out_csv, symbol=symbol, months=months, allow_partial=False)
            )
        except Exception as exc:  # excluded from the universe, never substituted
            results.append({"symbol": symbol, "excluded": True, "reason": str(exc)[:200]})
    manifest = {"development_months": months, "symbols": results}
    (out_dir / "manifest-dev.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def run_fetch_conf(repo_root: Path, contract: ModuleType) -> dict[str, Any]:
    months = _month_range(*contract.CLOSES_SOURCE["confirmation_months"])
    out_dir = _closes_dir(repo_root, contract)
    manifest_dev = json.loads((out_dir / "manifest-dev.json").read_text(encoding="utf-8"))
    universe = [
        row["symbol"]
        for row in manifest_dev["symbols"]
        if not row.get("excluded") and (row.get("complete", True) or row.get("cached"))
    ]
    results = []
    for symbol in universe:
        out_csv = out_dir / f"{symbol}-conf.csv"
        if out_csv.exists():
            results.append({"symbol": symbol, "path": out_csv.name, "cached": True})
            continue
        results.append(
            fetch_symbol_closes(out_csv, symbol=symbol, months=months, allow_partial=True)
        )
    manifest = {"confirmation_months": months, "symbols": results}
    (out_dir / "manifest-conf.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def load_universe_closes(
    repo_root: Path, contract: ModuleType, symbols: list[str], *, include_confirmation: bool
) -> pd.DataFrame:
    out_dir = _closes_dir(repo_root, contract)
    series = {}
    for symbol in symbols:
        frames = [pd.read_csv(out_dir / f"{symbol}-dev.csv")]
        if include_confirmation:
            conf_path = out_dir / f"{symbol}-conf.csv"
            if conf_path.exists():
                frames.append(pd.read_csv(conf_path))
        merged = pd.concat(frames).drop_duplicates("date").sort_values("date")
        index = pd.to_datetime(merged["date"], utc=True)
        series[symbol] = pd.Series(merged["close"].to_numpy(dtype=float), index=index)
    frame = pd.DataFrame(series).sort_index()
    return frame


def universe_coverage_errors(
    closes: pd.DataFrame, contract: ModuleType, start: str, end: str
) -> tuple[list[str], list[str]]:
    """Per-symbol interior-gap check over [start, end]; returns (universe, errors)."""
    max_gap = int(contract.DATA_QUALITY_GATES["max_daily_gap_days"])
    scope = closes.loc[str(start) : str(end)]
    universe: list[str] = []
    errors: list[str] = []
    for symbol in scope.columns:
        col = scope[symbol]
        valid = col.dropna()
        if valid.empty:
            errors.append(f"{symbol}: no data in window")
            continue
        gaps = pd.Series(valid.index).diff().dropna().dt.days
        if (gaps > max_gap).any():
            errors.append(f"{symbol}: interior gap > {max_gap} day(s)")
            continue
        universe.append(symbol)
    if len(universe) < int(contract.DATA_QUALITY_GATES["min_universe_size"]):
        errors.append(
            f"universe {len(universe)} below minimum "
            f"{contract.DATA_QUALITY_GATES['min_universe_size']}"
        )
    return universe, errors


# ---------------------------------------------------------------------------
# portfolio replay
# ---------------------------------------------------------------------------


def _rebalance_positions(closes: pd.DataFrame, start: str, end: str) -> list[int]:
    """Positional indices of Monday closes inside [start, end)."""
    index = closes.index
    mask = (index >= pd.Timestamp(start, tz="UTC")) & (index <= pd.Timestamp(end, tz="UTC"))
    positions = np.flatnonzero(mask & (index.dayofweek == 0))
    return [int(p) for p in positions]


def _rank_metric(closes: pd.DataFrame, pos: int, key: str, lookback: int) -> pd.Series:
    window_slice = closes.iloc[pos - lookback : pos + 1]
    if key in ("xs_mom_30d", "xs_rev_7d"):
        metric = window_slice.iloc[-1] / window_slice.iloc[0] - 1.0
    elif key == "xs_lowvol_30d":
        metric = window_slice.pct_change(fill_method=None).std()
    else:
        raise ValueError(f"unknown candidate key {key!r}")
    complete = window_slice.notna().all(axis=0)
    return metric.where(complete)


def _select_legs(metric: pd.Series, key: str, k: int) -> dict[str, int]:
    eligible = metric.dropna()
    # deterministic tie-break: metric desc, then symbol asc
    ordered = eligible.loc[sorted(eligible.index, key=lambda s: (-eligible[s], s))]
    top = list(ordered.index[:k])
    bottom = list(ordered.index[-k:])
    if key in ("xs_mom_30d",):
        longs, shorts = top, bottom
    elif key in ("xs_rev_7d", "xs_lowvol_30d"):
        longs, shorts = bottom, top
    else:
        raise ValueError(f"unknown candidate key {key!r}")
    legs = {symbol: 1 for symbol in longs}
    legs.update({symbol: -1 for symbol in shorts})
    return legs


def run_portfolio(
    closes: pd.DataFrame,
    contract: ModuleType,
    key: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    """Deterministic cash replay of one candidate over one window."""
    params = contract.PARAMETERS
    k = int(params["legs_per_side"])
    notional = float(params["leg_notional_usdt"])
    lookback = int(params["lookbacks_days"][key])
    min_universe = int(params["min_universe_size"])
    fee = {
        name: (spec["fee_bps_per_fill"] + spec["slippage_bps_per_fill"]) / 1e4
        for name, spec in contract.COST_SCENARIOS.items()
    }
    returns = closes.pct_change(fill_method=None)
    rebalances = _rebalance_positions(closes, start, end)
    if not rebalances or rebalances[0] < lookback + 1:
        raise ValueError("window has no rebalance with a full lookback")
    end_pos = int(
        np.flatnonzero(closes.index <= pd.Timestamp(end, tz="UTC") + pd.Timedelta(hours=23))[-1]
    )

    n_days = len(closes)
    daily_gross = np.zeros(n_days)
    daily_net_legs = np.zeros(n_days)
    daily_fees = {"base": np.zeros(n_days), "stress": np.zeros(n_days)}
    episodes: list[dict[str, Any]] = []
    open_episodes: dict[str, dict[str, Any]] = {}
    current_legs: dict[str, int] = {}

    def _close_episode(symbol: str, pos: int) -> None:
        episode = open_episodes.pop(symbol)
        episode["exit_pos"] = pos
        for name in ("base", "stress"):
            episode[f"{name}_pnl"] -= notional * fee[name]
            daily_fees[name][pos] += notional * fee[name]
        episodes.append(episode)

    checkpoints = rebalances + [end_pos]
    for idx, pos in enumerate(rebalances):
        metric = _rank_metric(closes, pos, key, lookback)
        eligible = int(metric.notna().sum())
        target = _select_legs(metric, key, k) if eligible >= min_universe else {}
        # close/flip legs that leave, open legs that enter
        for symbol in list(current_legs):
            if target.get(symbol) != current_legs[symbol]:
                _close_episode(symbol, pos)
                del current_legs[symbol]
        for symbol, sign in target.items():
            if symbol not in current_legs:
                current_legs[symbol] = sign
                open_episodes[symbol] = {
                    "symbol": symbol,
                    "sign": sign,
                    "entry_pos": pos,
                    "base_pnl": -notional * fee["base"],
                    "stress_pnl": -notional * fee["stress"],
                    "gross_pnl": 0.0,
                }
                daily_fees["base"][pos] += notional * fee["base"]
                daily_fees["stress"][pos] += notional * fee["stress"]
        # accrue returns until the next checkpoint (exclusive of the rebalance day itself)
        next_pos = checkpoints[idx + 1]
        for day in range(pos + 1, next_pos + 1):
            for symbol in list(current_legs):
                ret = returns.iloc[day][symbol]
                if np.isnan(ret):
                    # delisting rule: force-close at the last available close
                    _close_episode(symbol, day - 1)
                    del current_legs[symbol]
                    continue
                pnl = current_legs[symbol] * notional * float(ret)
                daily_gross[day] += pnl
                open_episodes[symbol]["gross_pnl"] += pnl
                open_episodes[symbol]["base_pnl"] += pnl
                open_episodes[symbol]["stress_pnl"] += pnl
            daily_net_legs[day] = sum(current_legs.values())
    for symbol in list(current_legs):
        _close_episode(symbol, end_pos)
        del current_legs[symbol]

    window_mask = (closes.index >= pd.Timestamp(start, tz="UTC")) & (
        closes.index <= pd.Timestamp(end, tz="UTC") + pd.Timedelta(hours=23)
    )
    gross = pd.Series(daily_gross, index=closes.index)[window_mask]
    base = gross - pd.Series(daily_fees["base"], index=closes.index)[window_mask]
    stress = gross - pd.Series(daily_fees["stress"], index=closes.index)[window_mask]
    month_index = base.index.tz_localize(None).to_period("M")
    monthly_base = base.groupby(month_index).sum()
    yearly_base = base.groupby(base.index.year).sum()
    best_leg = max((e["base_pnl"] for e in episodes), default=0.0)
    holding_days = [e["exit_pos"] - e["entry_pos"] for e in episodes]
    return {
        "gross_net_pnl": float(gross.sum()),
        "base_net_pnl": float(base.sum()),
        "stress_net_pnl": float(stress.sum()),
        "positive_months": int((monthly_base > 0).sum()),
        "months_total": int(monthly_base.shape[0]),
        "positive_years": int((yearly_base > 0).sum()),
        "closed_leg_positions": len(episodes),
        "leave_best_leg_base_net_pnl": float(base.sum() - best_leg),
        "mean_holding_days": float(np.mean(holding_days)) if holding_days else 0.0,
        "net_exposure_fraction": float(
            pd.Series(daily_net_legs, index=closes.index)[window_mask].mean() / (2 * k)
        ),
        "rebalances": len(rebalances),
        "daily_base_pnl_sha256": hashlib.sha256(
            np.round(base.to_numpy(), 10).tobytes()
        ).hexdigest(),
    }


# ---------------------------------------------------------------------------
# permutation null
# ---------------------------------------------------------------------------


def permutation_p_value(
    closes: pd.DataFrame,
    contract: ModuleType,
    key: str,
    start: str,
    end: str,
    candidate_base: float,
    *,
    n_trials: int | None = None,
    seed: int | None = None,
) -> float:
    """Random-ranking null with identical calendar, universe, legs, and costs."""
    params = contract.PARAMETERS
    k = int(params["legs_per_side"])
    notional = float(params["leg_notional_usdt"])
    lookback = int(params["lookbacks_days"][key])
    min_universe = int(params["min_universe_size"])
    base_fee = (
        contract.COST_SCENARIOS["base"]["fee_bps_per_fill"]
        + contract.COST_SCENARIOS["base"]["slippage_bps_per_fill"]
    ) / 1e4
    spec = contract.PERMUTATION_SPEC
    trials = int(n_trials or spec["n_trials"])
    rng = np.random.default_rng(seed if seed is not None else int(spec["seed"]))

    symbols = list(closes.columns)
    n_sym = len(symbols)
    returns = closes.pct_change(fill_method=None).to_numpy()
    rebalances = _rebalance_positions(closes, start, end)
    end_pos = int(
        np.flatnonzero(closes.index <= pd.Timestamp(end, tz="UTC") + pd.Timedelta(hours=23))[-1]
    )
    checkpoints = rebalances + [end_pos]

    totals = np.zeros(trials)
    weights = np.zeros((trials, n_sym))
    for idx, pos in enumerate(rebalances):
        metric = _rank_metric(closes, pos, key, lookback)
        eligible_mask = metric.notna().to_numpy()
        eligible_idx = np.flatnonzero(eligible_mask)
        new_weights = np.zeros((trials, n_sym))
        if eligible_idx.size >= min_universe:
            draws = rng.random((trials, eligible_idx.size))
            order = np.argsort(draws, axis=1)
            longs = eligible_idx[order[:, :k]]
            shorts = eligible_idx[order[:, -k:]]
            rows = np.repeat(np.arange(trials), k)
            new_weights[rows, longs.ravel()] = 1.0
            new_weights[rows, shorts.ravel()] = -1.0
        # |new - old| counts a side flip (+1 -> -1) as two fills, matching the replay
        fills = np.abs(new_weights - weights).sum(axis=1)
        totals -= fills * notional * base_fee
        weights = new_weights
        next_pos = checkpoints[idx + 1]
        segment = returns[pos + 1 : next_pos + 1]
        if segment.size:
            seg = np.nan_to_num(segment, nan=0.0)
            totals += (weights @ seg.sum(axis=0)) * notional
    totals -= np.abs(weights).sum(axis=1) * notional * base_fee  # final close
    exceed = int((totals >= candidate_base).sum())
    return (1 + exceed) / (trials + 1)


# ---------------------------------------------------------------------------
# gates + stages
# ---------------------------------------------------------------------------


def apply_gates(
    stage_gates: dict[str, Any],
    candidate: dict[str, Any],
    btc_bh_pnl_100usdt: float,
    p_value: float,
) -> dict[str, Any]:
    benchmark_floor = candidate["net_exposure_fraction"] * btc_bh_pnl_100usdt
    checks = {
        "base_net_pnl_positive": candidate["base_net_pnl"] > stage_gates["base_net_pnl_gt"],
        "stress_net_pnl_positive": candidate["stress_net_pnl"] > stage_gates["stress_net_pnl_gt"],
        "years_breadth": candidate["positive_years"]
        >= stage_gates["positive_calendar_years_at_least"],
        "months_breadth": candidate["positive_months"]
        >= stage_gates["positive_calendar_months_at_least"],
        "activity_floor": candidate["closed_leg_positions"]
        >= stage_gates["closed_leg_positions_at_least"],
        "leave_best_positive": candidate["leave_best_leg_base_net_pnl"]
        > stage_gates["leave_best_leg_base_net_pnl_gt"],
        "benchmark_relative": candidate["base_net_pnl"] > benchmark_floor,
        "permutation_p": p_value <= stage_gates["permutation_p_value_max"],
    }
    return {
        "checks": checks,
        "benchmark_floor": benchmark_floor,
        "permutation_p_value": p_value,
        "pass_gates": all(checks.values()),
    }


def _btc_bh_pnl_100usdt(closes: pd.DataFrame, start: str, end: str) -> float:
    btc = closes["BTCUSDT"].loc[str(start) : str(end)].dropna()
    return float(100.0 * (btc.iloc[-1] / btc.iloc[0] - 1.0))


def _fingerprint(candidate: dict[str, Any]) -> str:
    canonical = json.dumps(
        {k: round(v, 9) if isinstance(v, float) else v for k, v in candidate.items()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _resolve_universe(repo_root: Path, contract: ModuleType) -> list[str]:
    qual = json.loads(
        _output_path(repo_root, contract, "provider-qualification").read_text(encoding="utf-8")
    )
    if not qual.get("qualified"):
        raise SystemExit("provider qualification did not pass")
    if qual.get("contract_sha256") != contract.contract_sha256():
        raise SystemExit("contract drifted since qualification")
    return list(qual["universe"])


def evaluate_stage(
    repo_root: Path, contract: ModuleType, stage: str, keys: list[str]
) -> tuple[dict[str, Any], float]:
    start, end = contract.WINDOWS[stage]
    universe = _resolve_universe(repo_root, contract)
    closes = load_universe_closes(
        repo_root, contract, universe, include_confirmation=(stage == "confirmation")
    )
    btc_bh = _btc_bh_pnl_100usdt(closes, start, end)
    results: dict[str, Any] = {}
    for key in keys:
        replays = [run_portfolio(closes, contract, key, start, end) for _ in range(2)]
        fingerprints = [_fingerprint(r) for r in replays]
        reproducible = fingerprints[0] == fingerprints[1]
        candidate = replays[0]
        p_value = permutation_p_value(closes, contract, key, start, end, candidate["base_net_pnl"])
        gate_result = apply_gates(contract.GATES_V2[stage], candidate, btc_bh, p_value)
        source, model_version = contract.IDENTITIES[key]
        results[key] = {
            "key": key,
            "source": source,
            "model_version": model_version,
            **candidate,
            "gates": gate_result,
            "duplicate_replays": 2,
            "reproducible": reproducible,
            "replay_fingerprints": fingerprints,
            "pass_gates": gate_result["pass_gates"] and reproducible,
        }
    return results, btc_bh


def run_qualify(repo_root: Path, contract: ModuleType) -> dict[str, Any]:
    errors = contract.validate_contract()
    out_dir = _closes_dir(repo_root, contract)
    manifest_path = out_dir / "manifest-dev.json"
    universe: list[str] = []
    symbol_report: list[dict[str, Any]] = []
    if not manifest_path.exists():
        errors.append("manifest-dev.json missing; run fetch-dev first")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fetched = [row["symbol"] for row in manifest["symbols"] if not row.get("excluded")]
        symbol_report = manifest["symbols"]
        closes = load_universe_closes(repo_root, contract, fetched, include_confirmation=False)
        dev_end = contract.WINDOWS["development"][1]
        warmup_start = closes.index[0]
        universe, coverage_errors = universe_coverage_errors(
            closes, contract, str(warmup_start.date()), dev_end
        )
        # symbol-level gaps exclude symbols per the frozen universe rule; only a
        # universe below the contract minimum is a protocol-level failure
        errors.extend(e for e in coverage_errors if "below minimum" in e)
        excluded = sorted(set(fetched) - set(universe))
        if excluded or coverage_errors:
            symbol_report.append({"coverage_excluded": excluded, "coverage_notes": coverage_errors})
    payload = {
        "schema_version": f"{contract.SCHEMA_VERSION}.provider_qualification",
        "contract_sha256": contract.contract_sha256(),
        "symbol_pool": contract.SYMBOL_POOL,
        "universe": sorted(universe),
        "universe_size": len(universe),
        "symbols": symbol_report,
        "errors": errors,
        "qualified": not errors,
    }
    _output_path(repo_root, contract, "provider-qualification").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def run_develop(repo_root: Path, contract: ModuleType) -> dict[str, Any]:
    results, btc_bh = evaluate_stage(
        repo_root, contract, "development", sorted(contract.IDENTITIES)
    )
    passers = sorted(
        (key for key, row in results.items() if row["pass_gates"]),
        key=lambda key: (-results[key]["base_net_pnl"], key),
    )
    best = passers[0] if passers else None
    payload = {
        "schema_version": f"{contract.SCHEMA_VERSION}.development_results",
        "contract_sha256": contract.contract_sha256(),
        "window": list(contract.WINDOWS["development"]),
        "btc_buy_and_hold_pnl_100usdt": btc_bh,
        "candidates": results,
        "development_passers": passers,
        "best_candidate": best,
        "classification": (
            "development_pass_confirmation_open_eligible" if best else "development_rejected"
        ),
        "boundaries": {
            "writes_signal_events": False,
            "mutates_source_policy": False,
            "opens_future_blind": False,
            "opens_confirmation_early": False,
            "confirmation_data_fetched": False,
            "touches_live_path": False,
        },
    }
    _output_path(repo_root, contract, "development-results").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def run_confirm(repo_root: Path, contract: ModuleType) -> dict[str, Any]:
    development = json.loads(
        _output_path(repo_root, contract, "development-results").read_text(encoding="utf-8")
    )
    if not development.get("best_candidate"):
        raise SystemExit("development did not pass; confirmation stays sealed")
    if development.get("contract_sha256") != contract.contract_sha256():
        raise SystemExit("contract drifted since development")
    key = development["best_candidate"]
    run_fetch_conf(repo_root, contract)
    results, btc_bh = evaluate_stage(repo_root, contract, "confirmation", [key])
    row = results[key]
    payload = {
        "schema_version": f"{contract.SCHEMA_VERSION}.confirmation_results",
        "contract_sha256": contract.contract_sha256(),
        "window": list(contract.WINDOWS["confirmation"]),
        "btc_buy_and_hold_pnl_100usdt": btc_bh,
        "candidate": row,
        "pass_gates": row["pass_gates"],
        "classification": (
            "confirmation_passed_paper_shadow_eligible"
            if row["pass_gates"]
            else "confirmation_rejected"
        ),
        "boundaries": {
            "writes_signal_events": False,
            "mutates_source_policy": False,
            "opens_future_blind": False,
            "touches_live_path": False,
        },
    }
    _output_path(repo_root, contract, "confirmation-results").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("repo root with pyproject.toml not found")


def build_main(contract: ModuleType):
    """Build the thin per-protocol CLI entrypoint bound to one frozen contract."""

    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(description=contract.__doc__)
        parser.add_argument("command", choices=["fetch-dev", "qualify", "develop", "confirm"])
        parser.add_argument("--repo-root", type=Path, default=None)
        args = parser.parse_args(argv)
        repo_root = args.repo_root or _find_repo_root()
        if args.command == "fetch-dev":
            manifest = run_fetch_dev(repo_root, contract)
            excluded = [r["symbol"] for r in manifest["symbols"] if r.get("excluded")]
            print(json.dumps({"symbols": len(manifest["symbols"]), "excluded": excluded}))
            return 0
        if args.command == "qualify":
            payload = run_qualify(repo_root, contract)
            print(
                json.dumps(
                    {
                        "qualified": payload["qualified"],
                        "universe_size": payload["universe_size"],
                        "errors": payload["errors"],
                    }
                )
            )
            return 0 if payload["qualified"] else 1
        if args.command == "develop":
            payload = run_develop(repo_root, contract)
            summary = {
                "classification": payload["classification"],
                "best_candidate": payload["best_candidate"],
                "candidates": {
                    key: {
                        "base": round(row["base_net_pnl"], 4),
                        "p": round(row["gates"]["permutation_p_value"], 4),
                        "pass": row["pass_gates"],
                    }
                    for key, row in payload["candidates"].items()
                },
            }
            print(json.dumps(summary))
            return 0 if payload["best_candidate"] else 1
        payload = run_confirm(repo_root, contract)
        print(
            json.dumps(
                {
                    "classification": payload["classification"],
                    "base_net_pnl": payload["candidate"]["base_net_pnl"],
                    "checks": payload["candidate"]["gates"]["checks"],
                }
            )
        )
        return 0 if payload["pass_gates"] else 1

    return main
