"""Contract-parameterized harness for funding-rate state protocols (ADR-014 §6.4).

One shared implementation of the fetch → qualify → develop → confirm pipeline
for Binance funding-rate positioning-state protocols. Each protocol binds its
own frozen contract module (``apps.ops.research_protocol_v50``,
``research_protocol_v51``, ...) and exposes a thin CLI via ``build_main``.
Nothing evaluative lives here: rules, thresholds, windows, gates, and data
identities all come from the bound contract, and every stage output records
that contract's ``contract_sha256()``.

Stage outputs land at ``docs/progress/phase-2-research-<tag>-{provider-qualification,
development-results,confirmation-results}.json`` where ``<tag>`` is parsed from
the contract's ``SCHEMA_VERSION`` (e.g. ``research.protocol.v51.v1`` → ``v51``).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from types import ModuleType
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

_TS_COLUMNS = ("calc_time", "funding_time", "fundingtime")
_RATE_COLUMNS = ("last_funding_rate", "funding_rate", "fundingrate")

RULE_KEYS = ("fund_neg_3d", "fund_below_baseline_3d", "fund_overheat_flat_3d")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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


# ---------------------------------------------------------------------------
# fetch + parse
# ---------------------------------------------------------------------------


def _archive_dir(repo_root: Path, contract: ModuleType) -> Path:
    return repo_root / contract.FUNDING_SOURCE["archive_dir"]


def fetch_funding_months(
    repo_root: Path, contract: ModuleType, months: list[str]
) -> list[dict[str, Any]]:
    """One GET per monthly archive (+CHECKSUM); skips files already on disk."""
    out_dir = _archive_dir(repo_root, contract)
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol = contract.FUNDING_SOURCE["symbol"]
    base_url = contract.FUNDING_SOURCE["base_url"]
    manifest = []
    for month in months:
        name = f"{symbol}-fundingRate-{month}.zip"
        path = out_dir / name
        if not path.exists():
            url = f"{base_url}/{symbol}/{name}"
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


def load_funding(repo_root: Path, contract: ModuleType, months: list[str]) -> pd.Series:
    frames = []
    out_dir = _archive_dir(repo_root, contract)
    symbol = contract.FUNDING_SOURCE["symbol"]
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


def funding_quality_errors(
    report: dict[str, Any],
    *,
    min_settlements: int,
    max_gap_hours: float,
    rate_abs_max: float,
) -> list[str]:
    errors = []
    if report["settlements"] < min_settlements:
        errors.append(f"settlement count {report['settlements']} < {min_settlements}")
    if report["max_gap_hours"] is None or report["max_gap_hours"] > max_gap_hours:
        errors.append(f"max settlement gap {report['max_gap_hours']} hours exceeds ceiling")
    if report["abs_rate_max"] is None or report["abs_rate_max"] > rate_abs_max:
        errors.append(f"abs rate {report['abs_rate_max']} outside sanity range")
    return errors


# ---------------------------------------------------------------------------
# candidate states
# ---------------------------------------------------------------------------


def build_candidate_states(
    closes_window: pd.Series,
    funding: pd.Series,
    *,
    window_hours: int,
    min_settlements: int,
    baseline_rate: float,
    overheat_rate: float,
) -> dict[str, np.ndarray]:
    """Daily long/flat states for the three frozen rule shapes over one closes window."""
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
        if count >= min_settlements:
            total = cumsum[hi] - cumsum[lo]
            sums[i] = total
            means[i] = total / count
    valid = counts >= min_settlements
    return {
        "fund_neg_3d": valid & (sums < 0.0),
        "fund_below_baseline_3d": valid & (means < baseline_rate),
        "fund_overheat_flat_3d": valid & ~(means > overheat_rate),
    }


def _states_for_contract(
    contract: ModuleType, closes_window: pd.Series, funding: pd.Series
) -> dict[str, np.ndarray]:
    params = contract.PARAMETERS
    return build_candidate_states(
        closes_window,
        funding,
        window_hours=int(params["trailing_window_hours"]),
        min_settlements=int(params["min_settlements_in_window"]),
        baseline_rate=float(params["baseline_rate_per_8h"]),
        overheat_rate=float(params["overheat_rate_per_8h"]),
    )


def apply_gates(
    stage_gates: dict[str, Any],
    candidate: dict[str, Any],
    bh_pnl: float,
    p_value: float,
) -> dict[str, Any]:
    benchmark_floor = candidate["time_in_market_fraction"] * bh_pnl
    checks = {
        "base_net_pnl_positive": candidate["base_net_pnl"] > stage_gates["base_net_pnl_gt"],
        "stress_net_pnl_positive": candidate["stress_net_pnl"] > stage_gates["stress_net_pnl_gt"],
        "years_breadth": candidate["positive_years"]
        >= stage_gates["positive_calendar_years_at_least"],
        "months_breadth": candidate["positive_months"]
        >= stage_gates["positive_calendar_months_at_least"],
        "activity_floor": candidate["closed_positions"] >= stage_gates["closed_positions_at_least"],
        "leave_best_positive": candidate["leave_best_base_net_pnl"]
        > stage_gates["leave_best_position_base_net_pnl_gt"],
        "benchmark_relative": candidate["base_net_pnl"] > benchmark_floor,
        "bootstrap_p": p_value <= stage_gates["bootstrap_p_value_max"],
    }
    return {
        "checks": checks,
        "benchmark_floor": benchmark_floor,
        "bootstrap_p_value": p_value,
        "pass_gates": all(checks.values()),
    }


def fingerprint(states: np.ndarray, candidate: dict[str, Any]) -> str:
    payload = {
        "states_sha256": hashlib.sha256(np.packbits(states.astype(bool)).tobytes()).hexdigest(),
        "metrics": {k: round(v, 9) if isinstance(v, float) else v for k, v in candidate.items()},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def evaluate_stage(
    repo_root: Path, contract: ModuleType, stage: str, keys: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Shared develop/confirm evaluation for the given candidate keys."""
    windows = contract.WINDOWS
    start, end = windows["development"] if stage == "development" else windows["confirmation"]
    source = contract.FUNDING_SOURCE
    months = _month_range(
        source["development_months"][0],
        (
            source["development_months"][1]
            if stage == "development"
            else source["confirmation_months"][1]
        ),
    )
    funding = load_funding(repo_root, contract, months)
    closes = load_closes(repo_root / contract.CLOSES_SOURCE["csv_path"])
    closes_window = window(closes, start, end)
    trade_size = float(contract.TRADE_SIZE_BTC)
    bh = buy_and_hold_stats(closes_window, trade_size)

    results: dict[str, Any] = {}
    for key in keys:
        replays = []
        for _ in range(2):
            states = _states_for_contract(contract, closes_window, funding)[key]
            candidate = evaluate_long_flat_states(closes_window, states, trade_size)
            replays.append((states, candidate))
        fingerprints = [fingerprint(s, c) for s, c in replays]
        reproducible = fingerprints[0] == fingerprints[1]
        states, candidate = replays[0]
        p_value = matched_random_timing_p_value(
            closes_window,
            base_net_pnl=candidate["base_net_pnl"],
            time_in_market_fraction=candidate["time_in_market_fraction"],
            mean_holding_days=candidate["mean_holding_days"],
            trade_size=trade_size,
            n_trials=int(contract.BOOTSTRAP_SPEC["n_trials"]),
            seed=int(contract.BOOTSTRAP_SPEC["seed"]),
        )
        gate_result = apply_gates(contract.GATES_V2[stage], candidate, bh["pnl"], p_value)
        source_name, model_version = contract.IDENTITIES[key]
        results[key] = {
            "key": key,
            "source": source_name,
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


def run_fetch_dev(repo_root: Path, contract: ModuleType) -> dict[str, Any]:
    months = _month_range(*contract.FUNDING_SOURCE["development_months"])
    manifest = fetch_funding_months(repo_root, contract, months)
    closes_path = repo_root / contract.CLOSES_SOURCE["csv_path"]
    if not closes_path.exists():
        fetch_closes(
            closes_path,
            symbol=contract.CLOSES_SOURCE["symbol"],
            start_month=contract.CLOSES_SOURCE["start_month"],
            end_month=contract.CLOSES_SOURCE["end_month"],
        )
    payload = {
        "funding_archives": manifest,
        "closes_sha256": _sha256_file(closes_path),
    }
    manifest_path = _archive_dir(repo_root, contract) / "manifest-dev.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", "utf-8")
    return payload


def run_qualify(repo_root: Path, contract: ModuleType) -> dict[str, Any]:
    errors = contract.validate_contract()
    quality = contract.DATA_QUALITY_GATES
    months = _month_range(*contract.FUNDING_SOURCE["development_months"])
    scope_start = quality.get("quality_scope_start", contract.WINDOWS["development"][0])
    manifest_path = _archive_dir(repo_root, contract) / "manifest-dev.json"
    report = None
    closes_entry = None
    if not manifest_path.exists():
        errors.append("manifest-dev.json missing; run fetch-dev first")
    else:
        funding = load_funding(repo_root, contract, months)
        report = funding_quality_report(funding, scope_start, contract.WINDOWS["development"][1])
        errors.extend(
            funding_quality_errors(
                report,
                min_settlements=int(quality["min_development_settlements"]),
                max_gap_hours=float(quality["max_settlement_gap_hours"]),
                rate_abs_max=float(quality["rate_abs_sanity_max"]),
            )
        )
        closes_path = repo_root / contract.CLOSES_SOURCE["csv_path"]
        closes = load_closes(closes_path)
        closes_entry = {
            "path": contract.CLOSES_SOURCE["csv_path"],
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
        "schema_version": f"{contract.SCHEMA_VERSION}.provider_qualification",
        "contract_sha256": contract.contract_sha256(),
        "development_months": months,
        "quality_scope_start": scope_start,
        "funding_quality": report,
        "closes": closes_entry,
        "errors": errors,
        "qualified": not errors,
    }
    _output_path(repo_root, contract, "provider-qualification").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def run_develop(repo_root: Path, contract: ModuleType) -> dict[str, Any]:
    qual_path = _output_path(repo_root, contract, "provider-qualification")
    qualification = json.loads(qual_path.read_text(encoding="utf-8"))
    if not qualification.get("qualified"):
        raise SystemExit("provider qualification did not pass; development stays closed")
    if qualification.get("contract_sha256") != contract.contract_sha256():
        raise SystemExit("contract drifted since qualification")
    results, bh = evaluate_stage(repo_root, contract, "development", sorted(contract.IDENTITIES))
    passers = sorted(
        (key for key, row in results.items() if row["pass_gates"]),
        key=lambda key: (-results[key]["base_net_pnl"], key),
    )
    best = passers[0] if passers else None
    payload = {
        "schema_version": f"{contract.SCHEMA_VERSION}.development_results",
        "contract_sha256": contract.contract_sha256(),
        "window": list(contract.WINDOWS["development"]),
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
    _output_path(repo_root, contract, "development-results").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def run_confirm(repo_root: Path, contract: ModuleType) -> dict[str, Any]:
    dev_path = _output_path(repo_root, contract, "development-results")
    development = json.loads(dev_path.read_text(encoding="utf-8"))
    if not development.get("best_candidate"):
        raise SystemExit("development did not pass; confirmation stays sealed")
    if development.get("contract_sha256") != contract.contract_sha256():
        raise SystemExit("contract drifted since development")
    key = development["best_candidate"]
    source = contract.FUNDING_SOURCE
    quality = contract.DATA_QUALITY_GATES
    conf_months = _month_range(*source["confirmation_months"])
    manifest = fetch_funding_months(repo_root, contract, conf_months)
    manifest_path = _archive_dir(repo_root, contract) / "manifest-conf.json"
    manifest_path.write_text(
        json.dumps({"funding_archives": manifest}, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    all_months = _month_range(source["development_months"][0], source["confirmation_months"][1])
    funding = load_funding(repo_root, contract, all_months)
    conf_report = funding_quality_report(
        funding, contract.WINDOWS["confirmation"][0], contract.WINDOWS["confirmation"][1]
    )
    quality_errors = funding_quality_errors(
        conf_report,
        min_settlements=int(quality["min_confirmation_settlements"]),
        max_gap_hours=float(quality["max_settlement_gap_hours"]),
        rate_abs_max=float(quality["rate_abs_sanity_max"]),
    )
    if quality_errors:
        raise SystemExit(f"confirmation data quality failed: {quality_errors}")
    results, bh = evaluate_stage(repo_root, contract, "confirmation", [key])
    row = results[key]
    payload = {
        "schema_version": f"{contract.SCHEMA_VERSION}.confirmation_results",
        "contract_sha256": contract.contract_sha256(),
        "window": list(contract.WINDOWS["confirmation"]),
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
            payload = run_fetch_dev(repo_root, contract)
            print(json.dumps({"archives": len(payload["funding_archives"])}))
            return 0
        if args.command == "qualify":
            payload = run_qualify(repo_root, contract)
            print(json.dumps({"qualified": payload["qualified"], "errors": payload["errors"]}))
            return 0 if payload["qualified"] else 1
        if args.command == "develop":
            payload = run_develop(repo_root, contract)
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
