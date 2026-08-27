"""Executable pipeline for Research Protocol v49 (multi-factor panel ridge).

Subcommands (run in order; each fails closed):

- ``qualify``: verify every pinned factor snapshot SHA256, header, and the
  official closes CSV coverage; write the provider-qualification JSON. No
  factor values are analyzed in this step.
- ``develop``: assemble the panel, run the frozen monthly walk-forward for
  every alpha in the grid over the development OOS window, select alpha by
  base net PnL, apply Gates v2 (including benchmark-relative and bootstrap
  gates), duplicate-replay, and write the development results JSON.
- ``confirm``: allowed only when development passed; runs the identical
  pipeline with the frozen alpha over 2023-2025 once and writes the
  confirmation results JSON.

Everything evaluative is frozen in ``apps.ops.research_protocol_v49``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apps.ops.research_meta_analysis import (
    _simulate_states,
    _window_gate_metrics,
    buy_and_hold_stats,
    load_closes,
    window,
)
from apps.ops.research_protocol_v49 import (
    BOOTSTRAP_SPEC,
    CLOSES_SOURCE,
    FACTOR_SOURCES,
    GATES_V2,
    IDENTITIES,
    MODEL_SPEC,
    SCHEMA_VERSION,
    TRADE_SIZE_BTC,
    WINDOWS,
    contract_sha256,
    validate_contract,
)

QUALIFICATION_RELPATH = Path("docs/progress/phase-2-research-v49-provider-qualification.json")
DEVELOPMENT_RELPATH = Path("docs/progress/phase-2-research-v49-development-results.json")
CONFIRMATION_RELPATH = Path("docs/progress/phase-2-research-v49-confirmation-results.json")

MIN_TRAIN_FEATURES = 10
Z_MIN_OBS = 60
FFILL_LIMIT_DAYS = 7


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# panel assembly
# ---------------------------------------------------------------------------


def _parse_available_at(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_datetime(series.astype("int64"), utc=True)
    return pd.to_datetime(series, utc=True, format="mixed")


def load_factor_series(repo_root: Path, key: str) -> pd.Series:
    """Concatenate the pinned dev+conf snapshots into one availability-stamped series."""
    spec = FACTOR_SOURCES[key]
    frames = []
    for path_field in ("dev_path", "conf_path"):
        frame = pd.read_csv(repo_root / spec[path_field])
        if spec["value_column"] not in frame.columns or "available_at" not in frame.columns:
            raise ValueError(f"{key}: {spec[path_field]} missing required columns")
        frames.append(
            pd.DataFrame(
                {
                    "available_at": _parse_available_at(frame["available_at"]),
                    "value": frame[spec["value_column"]].astype(float),
                }
            )
        )
    merged = pd.concat(frames).sort_values("available_at")
    overlap = merged[merged.duplicated("available_at", keep=False)]
    if not overlap.empty:
        spread = overlap.groupby("available_at")["value"].agg(["min", "max"])
        mismatched = spread[(spread["max"] - spread["min"]).abs() > 1e-9]
        if not mismatched.empty:
            raise ValueError(f"{key}: dev/conf snapshots disagree on overlapping stamps")
    deduped = merged.drop_duplicates("available_at", keep="first")
    return pd.Series(
        deduped["value"].to_numpy(), index=pd.DatetimeIndex(deduped["available_at"]), name=key
    )


def build_panel(closes: pd.Series, factors: dict[str, pd.Series]) -> pd.DataFrame:
    """Align factor values to the BTC daily calendar per the frozen availability rule."""
    panel_dates = closes.index
    cutoff = panel_dates + pd.Timedelta(days=1)  # end of panel day D
    columns = {}
    tolerance = pd.Timedelta(days=FFILL_LIMIT_DAYS)
    cutoff_frame = pd.DataFrame({"cutoff": cutoff})
    for key, series in factors.items():
        source = pd.DataFrame({"available_at": series.index, key: series.to_numpy()})
        aligned = pd.merge_asof(
            cutoff_frame,
            source,
            left_on="cutoff",
            right_on="available_at",
            direction="backward",
            tolerance=tolerance,
        )
        columns[key] = aligned[key].to_numpy()
    return pd.DataFrame(columns, index=panel_dates)


def _expanding_z(series: pd.Series, min_obs: int = Z_MIN_OBS) -> pd.Series:
    mean = series.expanding(min_periods=min_obs).mean()
    std = series.expanding(min_periods=min_obs).std()
    return (series - mean) / std.replace(0.0, np.nan)


def build_features(closes: pd.Series, panel: pd.DataFrame) -> pd.DataFrame:
    features = {}
    for key in panel.columns:
        features[key] = _expanding_z(panel[key].diff(5))
    log_close = np.log(closes)
    log_ret = log_close.diff()
    features["btc_mom20"] = _expanding_z(log_close.diff(20))
    features["btc_rvol20"] = _expanding_z(log_ret.rolling(20).std())
    return pd.DataFrame(features, index=closes.index)


def build_label(closes: pd.Series) -> pd.Series:
    return np.log(closes).diff().shift(-1)


# ---------------------------------------------------------------------------
# ridge walk-forward
# ---------------------------------------------------------------------------


def _fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    n_features = x.shape[1]
    design = np.column_stack([x, np.ones(len(x))])
    penalty = np.diag([alpha] * n_features + [0.0])
    coef = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    return coef


def _predict_ridge(coef: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.column_stack([x, np.ones(len(x))]) @ coef


def run_walkforward(
    features: pd.DataFrame,
    label: pd.Series,
    *,
    alpha: float,
    predict_start: str,
    predict_end: str,
) -> pd.Series:
    """Monthly-refit expanding walk-forward; returns predicted next-day returns."""
    train_start = pd.Timestamp(WINDOWS["training_start"], tz="UTC")
    months = pd.period_range(
        pd.Timestamp(predict_start).to_period("M"),
        pd.Timestamp(predict_end).to_period("M"),
        freq="M",
    )
    min_train_months = int(MODEL_SPEC["min_train_months"])
    valid_feature_count = features.notna().sum(axis=1)
    predictions = pd.Series(np.nan, index=features.index, dtype=float)
    train_start_period = train_start.tz_localize(None).to_period("M")
    for month in months:
        month_start = month.to_timestamp(how="start").tz_localize("UTC")
        month_end = month.to_timestamp(how="end").tz_localize("UTC")
        if (month - train_start_period).n < min_train_months:
            raise ValueError(f"insufficient training months before {month_start.date()}")
        train_mask = (
            (features.index >= train_start)
            & (features.index < month_start)
            & label.notna()
            & (valid_feature_count >= MIN_TRAIN_FEATURES)
        )
        x_train = features.loc[train_mask].fillna(0.0).to_numpy()
        y_train = label.loc[train_mask].to_numpy()
        if len(x_train) < 40:
            raise ValueError(f"only {len(x_train)} training rows before {month_start.date()}")
        coef = _fit_ridge(x_train, y_train, alpha)
        predict_mask = (features.index >= month_start) & (features.index <= month_end)
        x_predict = features.loc[predict_mask].fillna(0.0).to_numpy()
        predictions.loc[predict_mask] = _predict_ridge(coef, x_predict)
    return predictions.loc[
        (predictions.index >= pd.Timestamp(predict_start, tz="UTC"))
        & (predictions.index <= pd.Timestamp(predict_end, tz="UTC"))
    ]


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------


def evaluate_states(closes_window: pd.Series, states: np.ndarray) -> dict[str, Any]:
    metrics = _window_gate_metrics(closes_window, states[None, :], TRADE_SIZE_BTC)
    held = np.concatenate([[False], states[:-1]])
    return {
        "base_net_pnl": float(metrics["base"][0]),
        "stress_net_pnl": float(metrics["stress"][0]),
        "positive_months": int(metrics["months_positive"][0]),
        "months_total": int(metrics["months_total"][0]),
        "positive_years": int(metrics["years_positive"][0]),
        "closed_positions": int(metrics["positions"][0]),
        "leave_best_base_net_pnl": float(metrics["leave_best"][0]),
        "time_in_market_fraction": float(held.mean()),
        "mean_holding_days": (
            float(held.sum() / metrics["positions"][0]) if metrics["positions"][0] else 0.0
        ),
    }


def bootstrap_p_value(
    closes_window: pd.Series,
    candidate: dict[str, Any],
    *,
    n_trials: int | None = None,
    seed: int | None = None,
) -> float:
    n = int(n_trials or BOOTSTRAP_SPEC["n_trials"])
    rng = np.random.default_rng(seed if seed is not None else int(BOOTSTRAP_SPEC["seed"]))
    fraction_center = candidate["time_in_market_fraction"]
    hold_center = max(candidate["mean_holding_days"], 1.5)
    frac_low = min(max(fraction_center - 0.15, 0.02), 0.9)
    frac_high = max(min(fraction_center + 0.15, 0.98), frac_low + 0.01)
    hold_low = max(1.5, hold_center / 2.0)
    hold_high = max(hold_low + 0.1, hold_center * 2.0)
    fraction = rng.uniform(frac_low, frac_high, size=n)
    hold = np.exp(rng.uniform(math.log(hold_low), math.log(hold_high), size=n))
    p_off = np.clip(1.0 / hold, 1e-6, 1.0)
    p_on = np.clip(fraction * p_off / np.maximum(1.0 - fraction, 1e-9), 1e-6, 1.0)
    initial = rng.random(n) < fraction
    states = _simulate_states(rng, len(closes_window), p_on, p_off, initial)
    metrics = _window_gate_metrics(closes_window, states, TRADE_SIZE_BTC)
    exceed = int((metrics["base"] >= candidate["base_net_pnl"]).sum())
    return (1 + exceed) / (n + 1)


def apply_gates(
    stage: str,
    candidate: dict[str, Any],
    bh_pnl: float,
    p_value: float,
) -> dict[str, Any]:
    gates = GATES_V2[stage]
    benchmark_floor = candidate["time_in_market_fraction"] * bh_pnl
    checks = {
        "base_net_pnl_positive": candidate["base_net_pnl"] > gates["base_net_pnl_gt"],
        "stress_net_pnl_positive": candidate["stress_net_pnl"] > gates["stress_net_pnl_gt"],
        "years_breadth": candidate["positive_years"] >= gates["positive_calendar_years_at_least"],
        "months_breadth": candidate["positive_months"]
        >= gates["positive_calendar_months_at_least"],
        "activity_floor": candidate["closed_positions"] >= gates["closed_positions_at_least"],
        "leave_best_positive": candidate["leave_best_base_net_pnl"]
        > gates["leave_best_position_base_net_pnl_gt"],
        "benchmark_relative": candidate["base_net_pnl"] > benchmark_floor,
        "bootstrap_p": p_value <= gates["bootstrap_p_value_max"],
    }
    return {
        "checks": checks,
        "benchmark_floor": benchmark_floor,
        "bootstrap_p_value": p_value,
        "pass_gates": all(checks.values()),
    }


def _fingerprint(predictions: pd.Series, candidate: dict[str, Any]) -> str:
    payload = {
        "preds_sha256": hashlib.sha256(
            np.round(predictions.fillna(0.0).to_numpy(), 12).tobytes()
        ).hexdigest(),
        "metrics": {k: round(v, 9) if isinstance(v, float) else v for k, v in candidate.items()},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# pipeline stages
# ---------------------------------------------------------------------------


def _load_inputs(repo_root: Path) -> tuple[pd.Series, pd.DataFrame, pd.Series]:
    closes = load_closes(repo_root / CLOSES_SOURCE["csv_path"])
    factors = {key: load_factor_series(repo_root, key) for key in sorted(FACTOR_SOURCES)}
    panel = build_panel(closes, factors)
    features = build_features(closes, panel)
    label = build_label(closes)
    return closes, features, label


def _run_candidate(
    closes: pd.Series,
    features: pd.DataFrame,
    label: pd.Series,
    *,
    alpha: float,
    start: str,
    end: str,
) -> tuple[pd.Series, np.ndarray, dict[str, Any]]:
    predictions = run_walkforward(
        features, label, alpha=alpha, predict_start=start, predict_end=end
    )
    closes_window = window(closes, start, end)
    if len(predictions) != len(closes_window):
        raise ValueError("prediction index does not match the evaluation window")
    states = (predictions.to_numpy() > 0.0).astype(bool)
    candidate = evaluate_states(closes_window, states)
    return predictions, states, candidate


def run_qualify(repo_root: Path) -> dict[str, Any]:
    errors = validate_contract()
    files = []
    for key, spec in sorted(FACTOR_SOURCES.items()):
        for path_field, sha_field in (("dev_path", "dev_sha256"), ("conf_path", "conf_sha256")):
            path = repo_root / spec[path_field]
            entry: dict[str, Any] = {"factor": key, "path": spec[path_field]}
            if not path.exists():
                errors.append(f"{key}: missing {spec[path_field]}")
                entry["status"] = "missing"
            else:
                digest = _sha256_file(path)
                entry["sha256"] = digest
                entry["status"] = "ok" if digest == spec[sha_field] else "sha256_mismatch"
                if entry["status"] != "ok":
                    errors.append(f"{key}: sha256 mismatch for {spec[path_field]}")
                header = path.open(encoding="utf-8").readline().strip().split(",")
                if spec["value_column"] not in header or "available_at" not in header:
                    errors.append(f"{key}: header missing required columns")
            files.append(entry)
    closes_path = repo_root / CLOSES_SOURCE["csv_path"]
    closes_entry: dict[str, Any] = {"path": CLOSES_SOURCE["csv_path"]}
    if not closes_path.exists():
        errors.append("closes CSV missing; run research_meta_analysis fetch-closes first")
    else:
        closes = load_closes(closes_path)
        closes_entry.update(
            {
                "sha256": _sha256_file(closes_path),
                "rows": int(len(closes)),
                "first_date": str(closes.index[0].date()),
                "last_date": str(closes.index[-1].date()),
            }
        )
        if str(closes.index[0].date()) > "2019-12-01" or str(closes.index[-1].date()) < (
            "2025-12-31"
        ):
            errors.append("closes CSV does not cover 2019-12-01..2025-12-31")
    payload = {
        "schema_version": f"{SCHEMA_VERSION}.provider_qualification",
        "contract_sha256": contract_sha256(),
        "factor_files": files,
        "closes": closes_entry,
        "errors": errors,
        "qualified": not errors,
    }
    (repo_root / QUALIFICATION_RELPATH).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def run_develop(repo_root: Path) -> dict[str, Any]:
    qualification = json.loads((repo_root / QUALIFICATION_RELPATH).read_text(encoding="utf-8"))
    if not qualification.get("qualified"):
        raise SystemExit("provider qualification did not pass; development stays closed")
    if qualification.get("contract_sha256") != contract_sha256():
        raise SystemExit("contract drifted since qualification")
    closes, features, label = _load_inputs(repo_root)
    start, end = WINDOWS["development_oos"]
    closes_window = window(closes, start, end)
    bh = buy_and_hold_stats(closes_window, TRADE_SIZE_BTC)

    per_alpha: dict[str, Any] = {}
    for alpha in MODEL_SPEC["alpha_grid"]:
        _, _, candidate = _run_candidate(closes, features, label, alpha=alpha, start=start, end=end)
        per_alpha[str(alpha)] = candidate
    best_alpha = max(
        MODEL_SPEC["alpha_grid"],
        key=lambda a: (per_alpha[str(a)]["base_net_pnl"], a),
    )
    predictions_a, _, candidate = _run_candidate(
        closes, features, label, alpha=best_alpha, start=start, end=end
    )
    predictions_b, _, candidate_b = _run_candidate(
        closes, features, label, alpha=best_alpha, start=start, end=end
    )
    fingerprints = [
        _fingerprint(predictions_a, candidate),
        _fingerprint(predictions_b, candidate_b),
    ]
    reproducible = fingerprints[0] == fingerprints[1]
    p_value = bootstrap_p_value(closes_window, candidate)
    gates = apply_gates("development", candidate, bh["pnl"], p_value)
    pass_gates = gates["pass_gates"] and reproducible
    source, model_version = IDENTITIES["panel_ridge"]
    payload = {
        "schema_version": f"{SCHEMA_VERSION}.development_results",
        "contract_sha256": contract_sha256(),
        "source": source,
        "model_version": model_version,
        "window": [start, end],
        "selected_alpha": best_alpha,
        "per_alpha_candidates": per_alpha,
        "candidate": candidate,
        "buy_and_hold": bh,
        "gates": gates,
        "duplicate_replays": 2,
        "reproducible": reproducible,
        "replay_fingerprints": fingerprints,
        "pass_gates": pass_gates,
        "classification": (
            "development_pass_confirmation_open_eligible" if pass_gates else "development_rejected"
        ),
        "boundaries": {
            "writes_signal_events": False,
            "mutates_source_policy": False,
            "opens_future_blind": False,
            "opens_confirmation_early": False,
            "touches_live_path": False,
        },
    }
    (repo_root / DEVELOPMENT_RELPATH).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def run_confirm(repo_root: Path) -> dict[str, Any]:
    development = json.loads((repo_root / DEVELOPMENT_RELPATH).read_text(encoding="utf-8"))
    if not development.get("pass_gates"):
        raise SystemExit("development did not pass; confirmation stays sealed")
    if development.get("contract_sha256") != contract_sha256():
        raise SystemExit("contract drifted since development")
    alpha = float(development["selected_alpha"])
    closes, features, label = _load_inputs(repo_root)
    start, end = WINDOWS["confirmation"]
    closes_window = window(closes, start, end)
    bh = buy_and_hold_stats(closes_window, TRADE_SIZE_BTC)
    predictions_a, _, candidate = _run_candidate(
        closes, features, label, alpha=alpha, start=start, end=end
    )
    predictions_b, _, candidate_b = _run_candidate(
        closes, features, label, alpha=alpha, start=start, end=end
    )
    fingerprints = [
        _fingerprint(predictions_a, candidate),
        _fingerprint(predictions_b, candidate_b),
    ]
    reproducible = fingerprints[0] == fingerprints[1]
    p_value = bootstrap_p_value(closes_window, candidate)
    gates = apply_gates("confirmation", candidate, bh["pnl"], p_value)
    pass_gates = gates["pass_gates"] and reproducible
    source, model_version = IDENTITIES["panel_ridge"]
    payload = {
        "schema_version": f"{SCHEMA_VERSION}.confirmation_results",
        "contract_sha256": contract_sha256(),
        "source": source,
        "model_version": model_version,
        "window": [start, end],
        "frozen_alpha": alpha,
        "candidate": candidate,
        "buy_and_hold": bh,
        "gates": gates,
        "duplicate_replays": 2,
        "reproducible": reproducible,
        "replay_fingerprints": fingerprints,
        "pass_gates": pass_gates,
        "classification": (
            "confirmation_passed_paper_shadow_eligible" if pass_gates else "confirmation_rejected"
        ),
        "boundaries": {
            "writes_signal_events": False,
            "mutates_source_policy": False,
            "opens_future_blind": False,
            "touches_live_path": False,
        },
    }
    (repo_root / CONFIRMATION_RELPATH).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("repo root with pyproject.toml not found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["qualify", "develop", "confirm"])
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    repo_root = args.repo_root or _find_repo_root()
    if args.command == "qualify":
        payload = run_qualify(repo_root)
        print(json.dumps({"qualified": payload["qualified"], "errors": payload["errors"]}))
        return 0 if payload["qualified"] else 1
    payload = run_develop(repo_root) if args.command == "develop" else run_confirm(repo_root)
    print(
        json.dumps(
            {
                "classification": payload["classification"],
                "base_net_pnl": payload["candidate"]["base_net_pnl"],
                "checks": payload["gates"]["checks"],
                "bootstrap_p_value": payload["gates"]["bootstrap_p_value"],
            }
        )
    )
    return 0 if payload["pass_gates"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
