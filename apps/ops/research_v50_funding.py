"""Executable pipeline for Research Protocol v50 (BTC funding-rate positioning states).

Subcommands (run in order; each fails closed):

- ``fetch-dev``: one GET per Binance Vision monthly fundingRate archive for the
  development months only (2019-12..2022-12), CHECKSUM-verified, plus the
  official spot 1d closes CSV. Confirmation months are refused here.
- ``qualify``: parse the development archives, apply the frozen data-quality
  gates (sanity range, settlement-gap ceiling, minimum settlement count),
  verify closes coverage, and write the provider-qualification JSON.
- ``develop``: build the three frozen candidate state series over 2020-2022,
  evaluate under Gates v2 (benchmark-relative + matched random-timing
  bootstrap), duplicate-replay, and write the development results JSON.
- ``confirm``: allowed only when development passed; fetches the confirmation
  months (first confirmation data access), re-applies data-quality gates, and
  evaluates ONLY the advanced candidate over 2023-2025 once.

Everything evaluative is frozen in ``apps.ops.research_protocol_v50``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apps.ops.research_meta_analysis import (
    _fetch_url,
    _month_range,
    _parse_checksum_file,
    buy_and_hold_stats,
    evaluate_long_flat_states,
    fetch_closes,
    load_closes,
    matched_random_timing_p_value,
    window,
)
from apps.ops.research_protocol_v50 import (
    BOOTSTRAP_SPEC,
    CLOSES_SOURCE,
    DATA_QUALITY_GATES,
    FUNDING_SOURCE,
    GATES_V2,
    IDENTITIES,
    PARAMETERS,
    TRADE_SIZE_BTC,
    WINDOWS,
    contract_sha256,
    validate_contract,
)

QUALIFICATION_RELPATH = Path("docs/progress/phase-2-research-v50-provider-qualification.json")
DEVELOPMENT_RELPATH = Path("docs/progress/phase-2-research-v50-development-results.json")
CONFIRMATION_RELPATH = Path("docs/progress/phase-2-research-v50-confirmation-results.json")

SCHEMA_VERSION_QUAL = "research.protocol.v50.v1.provider_qualification"

_TS_COLUMNS = tuple(FUNDING_SOURCE["timestamp_columns"]) + ("fundingtime",)
_RATE_COLUMNS = tuple(FUNDING_SOURCE["rate_columns"]) + ("fundingrate",)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# fetch + parse
# ---------------------------------------------------------------------------


def _archive_dir(repo_root: Path) -> Path:
    return repo_root / FUNDING_SOURCE["archive_dir"]


def fetch_funding_months(repo_root: Path, months: list[str]) -> list[dict[str, Any]]:
    """One GET per monthly archive (+CHECKSUM); skips files already on disk."""
    out_dir = _archive_dir(repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol = FUNDING_SOURCE["symbol"]
    manifest = []
    for month in months:
        name = f"{symbol}-fundingRate-{month}.zip"
        path = out_dir / name
        if not path.exists():
            url = f"{FUNDING_SOURCE['base_url']}/{symbol}/{name}"
            payload = _fetch_url(url)
            expected = _parse_checksum_file(_fetch_url(url + ".CHECKSUM"))
            digest = _sha256_bytes(payload)
            if digest != expected:
                raise ValueError(f"checksum mismatch for {name}: {digest} != {expected}")
            path.write_bytes(payload)
        manifest.append({"file": name, "sha256": _sha256_file(path)})
    return manifest


def parse_funding_zip(payload: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"expected one member in funding zip, got {names}")
        with archive.open(names[0]) as handle:
            frame = pd.read_csv(handle)
    normalized = {str(col).strip().lower(): col for col in frame.columns}
    ts_col = next((normalized[c] for c in _TS_COLUMNS if c in normalized), None)
    rate_col = next((normalized[c] for c in _RATE_COLUMNS if c in normalized), None)
    if ts_col is None or rate_col is None:
        raise ValueError(f"unrecognized funding schema: {list(frame.columns)}")
    stamps_raw = pd.to_numeric(frame[ts_col], errors="raise").astype("int64")
    unit = "us" if int(stamps_raw.iloc[0]) > 10**14 else "ms"
    stamps = pd.to_datetime(stamps_raw, unit=unit, utc=True)
    return pd.DataFrame({"timestamp": stamps, "rate": frame[rate_col].astype(float)}).sort_values(
        "timestamp"
    )


def load_funding(repo_root: Path, months: list[str]) -> pd.Series:
    frames = []
    out_dir = _archive_dir(repo_root)
    symbol = FUNDING_SOURCE["symbol"]
    for month in months:
        path = out_dir / f"{symbol}-fundingRate-{month}.zip"
        if not path.exists():
            raise FileNotFoundError(f"funding archive missing: {path}")
        frames.append(parse_funding_zip(path.read_bytes()))
    merged = pd.concat(frames).drop_duplicates("timestamp").sort_values("timestamp")
    return pd.Series(
        merged["rate"].to_numpy(), index=pd.DatetimeIndex(merged["timestamp"]), name="funding"
    )


def funding_quality_report(funding: pd.Series, start: str, end: str) -> dict[str, Any]:
    scope = funding.loc[str(start) : str(end)]
    gaps_hours = (
        pd.Series(scope.index).diff().dropna().dt.total_seconds() / 3600.0
        if len(scope) > 1
        else pd.Series(dtype=float)
    )
    return {
        "settlements": int(len(scope)),
        "first": str(scope.index[0]) if len(scope) else None,
        "last": str(scope.index[-1]) if len(scope) else None,
        "max_gap_hours": float(gaps_hours.max()) if len(gaps_hours) else None,
        "abs_rate_max": float(scope.abs().max()) if len(scope) else None,
    }


def funding_quality_errors(report: dict[str, Any], *, min_settlements: int) -> list[str]:
    errors = []
    if report["settlements"] < min_settlements:
        errors.append(f"settlement count {report['settlements']} < {min_settlements}")
    if (
        report["max_gap_hours"] is None
        or report["max_gap_hours"] > DATA_QUALITY_GATES["max_settlement_gap_hours"]
    ):
        errors.append(f"max settlement gap {report['max_gap_hours']} hours exceeds ceiling")
    if (
        report["abs_rate_max"] is None
        or report["abs_rate_max"] > DATA_QUALITY_GATES["rate_abs_sanity_max"]
    ):
        errors.append(f"abs rate {report['abs_rate_max']} outside sanity range")
    return errors


# ---------------------------------------------------------------------------
# candidate states
# ---------------------------------------------------------------------------


def build_candidate_states(closes_window: pd.Series, funding: pd.Series) -> dict[str, np.ndarray]:
    """Daily long/flat states for the three frozen rules over one closes window."""
    window_hours = int(PARAMETERS["trailing_window_hours"])
    min_n = int(PARAMETERS["min_settlements_in_window"])
    baseline = float(PARAMETERS["baseline_rate_per_8h"])
    overheat = float(PARAMETERS["overheat_rate_per_8h"])
    stamps = funding.index.asi8
    rates = funding.to_numpy()
    cumsum = np.concatenate([[0.0], np.cumsum(rates)])
    n_days = len(closes_window)
    sums = np.full(n_days, np.nan)
    means = np.full(n_days, np.nan)
    counts = np.zeros(n_days, dtype=int)
    for i, day in enumerate(closes_window.index):
        cutoff = (day + pd.Timedelta(days=1)).value
        start = cutoff - window_hours * 3_600_000_000_000
        lo = np.searchsorted(stamps, start, side="left")
        hi = np.searchsorted(stamps, cutoff, side="left")
        count = hi - lo
        counts[i] = count
        if count >= min_n:
            total = cumsum[hi] - cumsum[lo]
            sums[i] = total
            means[i] = total / count
    valid = counts >= min_n
    return {
        "fund_neg_3d": valid & (sums < 0.0),
        "fund_below_baseline_3d": valid & (means < baseline),
        "fund_overheat_flat_3d": valid & ~(means > overheat),
    }


def _apply_gates(
    stage: str, candidate: dict[str, Any], bh_pnl: float, p_value: float
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


def _fingerprint(states: np.ndarray, candidate: dict[str, Any]) -> str:
    payload = {
        "states_sha256": hashlib.sha256(np.packbits(states.astype(bool)).tobytes()).hexdigest(),
        "metrics": {k: round(v, 9) if isinstance(v, float) else v for k, v in candidate.items()},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _evaluate_stage(
    repo_root: Path, stage: str, keys: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Shared develop/confirm evaluation for the given candidate keys."""
    start, end = WINDOWS["development"] if stage == "development" else WINDOWS["confirmation"]
    months = _month_range(
        FUNDING_SOURCE["development_months"][0],
        (
            FUNDING_SOURCE["development_months"][1]
            if stage == "development"
            else FUNDING_SOURCE["confirmation_months"][1]
        ),
    )
    funding = load_funding(repo_root, months)
    closes = load_closes(repo_root / CLOSES_SOURCE["csv_path"])
    closes_window = window(closes, start, end)
    bh = buy_and_hold_stats(closes_window, TRADE_SIZE_BTC)

    results: dict[str, Any] = {}
    for key in keys:
        replays = []
        for _ in range(2):
            states = build_candidate_states(closes_window, funding)[key]
            candidate = evaluate_long_flat_states(closes_window, states, TRADE_SIZE_BTC)
            replays.append((states, candidate))
        fingerprints = [_fingerprint(s, c) for s, c in replays]
        reproducible = fingerprints[0] == fingerprints[1]
        states, candidate = replays[0]
        p_value = matched_random_timing_p_value(
            closes_window,
            base_net_pnl=candidate["base_net_pnl"],
            time_in_market_fraction=candidate["time_in_market_fraction"],
            mean_holding_days=candidate["mean_holding_days"],
            trade_size=TRADE_SIZE_BTC,
            n_trials=int(BOOTSTRAP_SPEC["n_trials"]),
            seed=int(BOOTSTRAP_SPEC["seed"]),
        )
        gate_result = _apply_gates(stage, candidate, bh["pnl"], p_value)
        source, model_version = IDENTITIES[key]
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
    return results, bh


# ---------------------------------------------------------------------------
# pipeline stages
# ---------------------------------------------------------------------------


def run_fetch_dev(repo_root: Path) -> dict[str, Any]:
    months = _month_range(*FUNDING_SOURCE["development_months"])
    manifest = fetch_funding_months(repo_root, months)
    closes_path = repo_root / CLOSES_SOURCE["csv_path"]
    if not closes_path.exists():
        fetch_closes(
            closes_path,
            symbol=CLOSES_SOURCE["symbol"],
            start_month=CLOSES_SOURCE["start_month"],
            end_month=CLOSES_SOURCE["end_month"],
        )
    payload = {
        "funding_archives": manifest,
        "closes_sha256": _sha256_file(closes_path),
    }
    manifest_path = _archive_dir(repo_root) / "manifest-dev.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", "utf-8")
    return payload


def run_qualify(repo_root: Path) -> dict[str, Any]:
    errors = validate_contract()
    months = _month_range(*FUNDING_SOURCE["development_months"])
    manifest_path = _archive_dir(repo_root) / "manifest-dev.json"
    if not manifest_path.exists():
        errors.append("manifest-dev.json missing; run fetch-dev first")
        report = None
        closes_entry = None
    else:
        funding = load_funding(repo_root, months)
        report = funding_quality_report(funding, "2019-12-29", WINDOWS["development"][1])
        errors.extend(
            funding_quality_errors(
                report,
                min_settlements=int(DATA_QUALITY_GATES["min_development_settlements"]),
            )
        )
        closes_path = repo_root / CLOSES_SOURCE["csv_path"]
        closes = load_closes(closes_path)
        closes_entry = {
            "path": CLOSES_SOURCE["csv_path"],
            "sha256": _sha256_file(closes_path),
            "rows": int(len(closes)),
            "first_date": str(closes.index[0].date()),
            "last_date": str(closes.index[-1].date()),
        }
        if closes_entry["first_date"] > "2019-12-01" or closes_entry["last_date"] < "2025-12-31":
            errors.append("closes CSV does not cover 2019-12-01..2025-12-31")
        archives = json.loads(manifest_path.read_text(encoding="utf-8"))["funding_archives"]
        if len(archives) != len(months):
            errors.append(f"expected {len(months)} archives, manifest has {len(archives)}")
    payload = {
        "schema_version": SCHEMA_VERSION_QUAL,
        "contract_sha256": contract_sha256(),
        "development_months": months,
        "funding_quality": report,
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
    results, bh = _evaluate_stage(repo_root, "development", sorted(IDENTITIES))
    passers = sorted(
        (key for key, row in results.items() if row["pass_gates"]),
        key=lambda key: (-results[key]["base_net_pnl"], key),
    )
    best = passers[0] if passers else None
    payload = {
        "schema_version": "research.protocol.v50.v1.development_results",
        "contract_sha256": contract_sha256(),
        "window": list(WINDOWS["development"]),
        "buy_and_hold": bh,
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
    (repo_root / DEVELOPMENT_RELPATH).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def run_confirm(repo_root: Path) -> dict[str, Any]:
    development = json.loads((repo_root / DEVELOPMENT_RELPATH).read_text(encoding="utf-8"))
    if not development.get("best_candidate"):
        raise SystemExit("development did not pass; confirmation stays sealed")
    if development.get("contract_sha256") != contract_sha256():
        raise SystemExit("contract drifted since development")
    key = development["best_candidate"]
    conf_months = _month_range(*FUNDING_SOURCE["confirmation_months"])
    manifest = fetch_funding_months(repo_root, conf_months)
    manifest_path = _archive_dir(repo_root) / "manifest-conf.json"
    manifest_path.write_text(
        json.dumps({"funding_archives": manifest}, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    all_months = _month_range(
        FUNDING_SOURCE["development_months"][0], FUNDING_SOURCE["confirmation_months"][1]
    )
    funding = load_funding(repo_root, all_months)
    conf_report = funding_quality_report(
        funding, WINDOWS["confirmation"][0], WINDOWS["confirmation"][1]
    )
    quality_errors = funding_quality_errors(
        conf_report,
        min_settlements=int(DATA_QUALITY_GATES["min_confirmation_settlements"]),
    )
    if quality_errors:
        raise SystemExit(f"confirmation data quality failed: {quality_errors}")
    results, bh = _evaluate_stage(repo_root, "confirmation", [key])
    row = results[key]
    payload = {
        "schema_version": "research.protocol.v50.v1.confirmation_results",
        "contract_sha256": contract_sha256(),
        "window": list(WINDOWS["confirmation"]),
        "buy_and_hold": bh,
        "funding_quality": conf_report,
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
    parser.add_argument("command", choices=["fetch-dev", "qualify", "develop", "confirm"])
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    repo_root = args.repo_root or _find_repo_root()
    if args.command == "fetch-dev":
        payload = run_fetch_dev(repo_root)
        print(json.dumps({"archives": len(payload["funding_archives"])}))
        return 0
    if args.command == "qualify":
        payload = run_qualify(repo_root)
        print(json.dumps({"qualified": payload["qualified"], "errors": payload["errors"]}))
        return 0 if payload["qualified"] else 1
    if args.command == "develop":
        payload = run_develop(repo_root)
        summary = {
            "classification": payload["classification"],
            "best_candidate": payload["best_candidate"],
            "candidates": {
                key: {
                    "base": round(row["base_net_pnl"], 4),
                    "p": round(row["gates"]["bootstrap_p_value"], 4),
                    "pass": row["pass_gates"],
                }
                for key, row in payload["candidates"].items()
            },
        }
        print(json.dumps(summary))
        return 0 if payload["best_candidate"] else 1
    payload = run_confirm(repo_root)
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


if __name__ == "__main__":
    raise SystemExit(main())
