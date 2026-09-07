"""Collect one immutable Protocol v16 Treasury/BTC paper-shadow attempt.

This collector is credential-free and consumer-policy aware, but it is not a
paper execution runtime. It only preserves official Treasury snapshots,
closed public BTCUSDT hourly bars, dry-run ``SignalEvent v1`` rows, and an
append-only qualification journal under a gitignored data directory.
"""

from __future__ import annotations

import argparse
import base64
import csv
import fcntl
import hashlib
import io
import json
import math
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from apps.bridge.store import SignalStore
from apps.ops.research_protocol_v16 import IDENTITIES, PARAMETERS
from apps.ops.research_shadow_runtime import (
    atomic_json,
    captured_btc_observations,
    summarize_qualified,
)
from apps.ops.research_v8_shadow_daily import (
    _git_state,
    _merge_observations,
    _parse_btc_bars,
    _strict_json,
)
from apps.strategies_freqtrade.research.treasury_rate_signals import (
    generate_treasury_rate_signals,
)

CONTRACT_PATH = Path("docs/progress/phase-2-research-v16-paper-shadow.json")
SCHEMA_VERSION = "research.v16.paper_shadow_attempt.v1"
SNAPSHOT_SCHEMA_VERSION = "research.raw_snapshot.v16.paper_shadow.v1"
STATUS_SCHEMA_VERSION = "research.v16.paper_shadow_forward_status.v1"
CANDIDATE = "treasury_volatility_relief"
SOURCE, MODEL_VERSION = IDENTITIES[CANDIDATE]
Fetch = Callable[[str], bytes]


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _strict_json(path.read_bytes())
    if not isinstance(contract, dict):
        raise ValueError("v16 paper-shadow contract must be an object")
    if contract.get("schema_version") != "research.v16.paper_shadow_contract.v1":
        raise ValueError("v16 paper-shadow contract schema drifted")
    if contract.get("status") != "prospectively_locked":
        raise ValueError("v16 paper-shadow collection is not prospectively locked")
    if contract.get("candidate") != {
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "strategy": CANDIDATE,
        "symbol": "BTCUSDT",
        "venue": "BINANCE",
    }:
        raise ValueError("v16 paper-shadow candidate identity drifted")
    if contract.get("policy") != {
        "stage": "paper_shadow",
        "dry_run": True,
        "position_pct_multiplier": 0.2,
        "min_confidence_override": None,
    }:
        raise ValueError("v16 paper-shadow policy drifted")
    collection = contract.get("collection", {})
    if collection.get("decision_lag_calendar_days") != 2:
        raise ValueError("v16 paper-shadow D+2 decision lag drifted")
    if collection.get("treasury_route_params") != {
        "type": "daily_treasury_yield_curve",
        "field_tdr_date_value": "{year}",
        "page": "",
        "_format": "csv",
    }:
        raise ValueError("v16 paper-shadow Treasury route drifted")
    if collection.get("collector_implemented") is not True:
        raise ValueError("v16 paper-shadow collector is not marked implemented")
    if collection.get("scheduler_installed") is not False:
        raise ValueError("v16 paper-shadow contract must not install a scheduler")
    if collection.get("scheduler_install_requires_explicit_operator_approval") is not True:
        raise ValueError("v16 paper-shadow scheduler approval boundary drifted")
    if any(contract.get("boundaries", {}).values()):
        raise ValueError("v16 paper-shadow trading boundaries must remain false")
    gate = contract.get("evidence_gate", {})
    if gate.get("operator") != "or":
        raise ValueError("v16 paper-shadow evidence operator drifted")
    return contract


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-v16-paper-shadow"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def treasury_request_specs(
    contract: dict[str, Any], observed_at: datetime
) -> list[dict[str, Any]]:
    collection = contract["collection"]
    years = (observed_at.year - 1, observed_at.year)
    specs: list[dict[str, Any]] = []
    for year in years:
        params = {
            key: str(value).format(year=year)
            for key, value in collection["treasury_route_params"].items()
        }
        base = collection["treasury_url_template"].format(year=year)
        specs.append(
            {
                "year": year,
                "url": f"{base}?{urllib.parse.urlencode(params)}",
            }
        )
    return specs


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _parse_date(value: str) -> date:
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            pass
    raise ValueError(f"invalid Treasury date {value!r}")


def parse_treasury_csv(
    raw: bytes, *, year: int, target_day: date
) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Treasury response must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    normalized = {_normalize(field): field for field in reader.fieldnames or []}
    if "date" not in normalized or "10 yr" not in normalized:
        raise ValueError("Treasury response is missing Date or 10 YR")
    rows: list[dict[str, Any]] = []
    seen: set[date] = set()
    for index, row in enumerate(reader):
        observation_day = _parse_date(str(row[normalized["date"]]))
        if observation_day.year != year:
            raise ValueError(f"Treasury row {index} escaped requested year {year}")
        if observation_day in seen:
            raise ValueError("Treasury observation dates must be unique per response")
        seen.add(observation_day)
        if observation_day > target_day:
            continue
        raw_value = str(row[normalized["10 yr"]]).strip()
        if raw_value in {"", "N/A", "n/a", "."}:
            continue
        value = float(raw_value)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("Treasury 10-year yields must be finite and non-negative")
        rows.append(
            {
                "observation_date": observation_day.isoformat(),
                "nominal_10y": format(value, ".12g"),
            }
        )
    return rows


def parse_and_audit_treasury(
    payloads: list[tuple[dict[str, Any], bytes]], *, target_day: date
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(payloads) != 2:
        raise ValueError("v16 paper shadow requires previous/current Treasury years")
    rows: list[dict[str, Any]] = []
    annual_counts: dict[str, int] = {}
    expected_years = [int(spec["year"]) for spec, _ in payloads]
    if expected_years[1] != expected_years[0] + 1:
        raise ValueError("Treasury paper-shadow years must be consecutive")
    for spec, raw in payloads:
        year = int(spec["year"])
        annual = parse_treasury_csv(raw, year=year, target_day=target_day)
        annual_counts[str(year)] = len(annual)
        rows.extend(annual)
    rows.sort(key=lambda row: row["observation_date"])
    days = [date.fromisoformat(row["observation_date"]) for row in rows]
    if len(rows) < int(PARAMETERS[CANDIDATE]["long_observations"]) + 1:
        raise ValueError("Treasury paper-shadow warmup coverage is insufficient")
    if len(days) != len(set(days)):
        raise ValueError("Treasury paper-shadow observation dates must be unique")
    max_gap = max(
        (right - left).days for left, right in zip(days, days[1:], strict=False)
    )
    return rows, {
        "annual_numeric_row_counts": annual_counts,
        "row_count": len(rows),
        "first_date": days[0].isoformat(),
        "last_date": days[-1].isoformat(),
        "target_eligible_observation_date": target_day.isoformat(),
        "maximum_calendar_gap_days": max_gap,
        "forward_fill_used": False,
    }


def _write_treasury_snapshot(
    *,
    payloads: list[tuple[dict[str, Any], bytes]],
    audit: dict[str, Any],
    observed_at: datetime,
    contract_sha256: str,
    output_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    records = [
        {
            **spec,
            "payload_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
            "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
        }
        for spec, raw in payloads
    ]
    core = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "retrieved_at": observed_at.isoformat().replace("+00:00", "Z"),
        "contract_sha256": contract_sha256,
        "requests": records,
        "audit": audit,
        "boundaries": {
            "credentials_loaded": False,
            "orders_submitted": False,
            "fills_created": False,
            "paper_simulated_touched": False,
            "testnet_touched": False,
            "live_path_touched": False,
            "future_blind_opened": False,
        },
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    envelope = {
        **core,
        "snapshot_sha256": f"sha256:{digest}",
        "vintage_id": f"treasury-v16-paper-shadow:{observed_at.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (
        f"treasury-paper-shadow-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    )
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    verify_snapshot(path)
    return path, envelope


def verify_snapshot(
    path: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    envelope = _strict_json(path.read_bytes())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != (
        SNAPSHOT_SCHEMA_VERSION
    ):
        raise ValueError("invalid v16 paper-shadow snapshot schema")
    contract = load_contract(contract_path)
    contract_sha256 = f"sha256:{hashlib.sha256(contract_path.read_bytes()).hexdigest()}"
    if envelope.get("contract_sha256") != contract_sha256:
        raise ValueError("v16 paper-shadow snapshot contract fingerprint mismatch")
    try:
        observed_at = datetime.fromisoformat(
            str(envelope["retrieved_at"]).replace("Z", "+00:00")
        ).astimezone(UTC)
        target_day = date.fromisoformat(
            str(envelope["audit"]["target_eligible_observation_date"])
        )
    except (KeyError, ValueError) as exc:
        raise ValueError("v16 paper-shadow snapshot dates are invalid") from exc
    expected_specs = treasury_request_specs(contract, observed_at)
    records = envelope.get("requests")
    if not isinstance(records, list) or len(records) != len(expected_specs):
        raise ValueError("v16 paper-shadow snapshot request count mismatch")
    payloads: list[tuple[dict[str, Any], bytes]] = []
    for expected, record in zip(expected_specs, records, strict=True):
        if any(record.get(key) != expected[key] for key in ("year", "url")):
            raise ValueError("v16 paper-shadow Treasury request identity drifted")
        raw = base64.b64decode(str(record.get("payload_raw_base64")), validate=True)
        if record.get("payload_sha256") != f"sha256:{hashlib.sha256(raw).hexdigest()}":
            raise ValueError("v16 paper-shadow Treasury payload fingerprint mismatch")
        payloads.append((expected, raw))
    _, audit = parse_and_audit_treasury(payloads, target_day=target_day)
    if envelope.get("audit") != audit:
        raise ValueError("v16 paper-shadow snapshot audit mismatch")
    core = {
        key: value
        for key, value in envelope.items()
        if key not in {"snapshot_sha256", "vintage_id"}
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if envelope.get("snapshot_sha256") != f"sha256:{digest}":
        raise ValueError("v16 paper-shadow snapshot digest mismatch")
    if not str(envelope.get("vintage_id", "")).endswith(digest[:12]):
        raise ValueError("v16 paper-shadow snapshot vintage mismatch")
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "path": str(path),
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def _factor_frame(
    rows: list[dict[str, Any]], *, snapshot_sha256: str, vintage_id: str
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in rows:
        observation = pd.Timestamp(row["observation_date"], tz="UTC")
        available = observation + pd.Timedelta(days=2)
        records.append(
            {
                "ts_event": available,
                "nominal_10y": float(row["nominal_10y"]),
                "available_at": available,
                "snapshot_sha256": snapshot_sha256,
                "vintage_id": vintage_id,
            }
        )
    return pd.DataFrame(records).set_index("ts_event").sort_index()


def summarize_attempts(
    records: list[dict[str, Any]], *, gate_days: int, gate_signals: int
) -> dict[str, Any]:
    status = summarize_qualified(records, gate_days=gate_days, gate_signals=gate_signals)
    status.update(schema_version=STATUS_SCHEMA_VERSION, automatic_paper_simulated_authorization=False)
    return status


def collect_daily(
    *,
    repo_root: Path,
    data_root: Path,
    contract_path: Path = CONTRACT_PATH,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
    git_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    contract = load_contract(contract_path)
    contract_sha256 = f"sha256:{hashlib.sha256(contract_path.read_bytes()).hexdigest()}"
    collection = contract["collection"]
    target_day = observed_at.date() - timedelta(
        days=int(collection["decision_lag_calendar_days"])
    )
    data_root.mkdir(parents=True, exist_ok=True)
    with (data_root / ".collector.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raw_dir = data_root / "raw"
        state_dir = data_root / "state"
        journal_dir = data_root / "journal"
        for directory in (raw_dir, state_dir, journal_dir):
            directory.mkdir(parents=True, exist_ok=True)

        repo = git_state or _git_state(repo_root)
        specs = treasury_request_specs(contract, observed_at)
        payloads = [(spec, fetch(spec["url"])) for spec in specs]
        treasury_rows, treasury_audit = parse_and_audit_treasury(
            payloads, target_day=target_day
        )
        snapshot_path, snapshot = _write_treasury_snapshot(
            payloads=payloads,
            audit=treasury_audit,
            observed_at=observed_at,
            contract_sha256=contract_sha256,
            output_dir=raw_dir / "treasury",
        )

        btc_url = str(collection["btc_url"])
        btc_raw = fetch(btc_url)
        btc_bars = _parse_btc_bars(btc_raw, observed_at=observed_at)
        attempt_id = (
            f"{observed_at.strftime('%Y%m%dT%H%M%SZ')}-"
            f"{snapshot['snapshot_sha256'][-12:]}"
        )
        btc_path = raw_dir / "btc" / f"btc-1h-{attempt_id}.json"
        btc_path.parent.mkdir(parents=True, exist_ok=True)
        if btc_path.exists():
            raise FileExistsError(f"refusing to overwrite {btc_path}")
        btc_path.write_bytes(btc_raw)

        treasury_state_path = state_dir / "treasury-nominal10-observations.json"
        previous_treasury = (
            _strict_json(treasury_state_path.read_bytes())
            if treasury_state_path.exists()
            else {}
        )
        current_treasury = {
            row["observation_date"]: row["nominal_10y"] for row in treasury_rows
        }
        merged_treasury, treasury_revisions, new_treasury_rows = _merge_observations(
            previous_treasury, current_treasury
        )

        btc_state_path = state_dir / "btc-hourly-observations.json"
        previous_btc = (
            _strict_json(btc_state_path.read_bytes()) if btc_state_path.exists() else {}
        )
        previous_btc = captured_btc_observations(previous_btc, journal_dir)
        current_btc = {str(row["open_time_ms"]): row for row in btc_bars}
        merged_btc, btc_revisions, new_btc_rows = _merge_observations(
            previous_btc, current_btc
        )
        btc_times = sorted(int(value) for value in merged_btc)
        btc_contiguous = all(
            right - left == 3_600_000
            for left, right in zip(btc_times, btc_times[1:], strict=False)
        )

        frame = _factor_frame(
            treasury_rows,
            snapshot_sha256=snapshot["snapshot_sha256"],
            vintage_id=snapshot["vintage_id"],
        )
        events = generate_treasury_rate_signals(
            frame,
            candidate=CANDIDATE,
            start_date=treasury_rows[0]["observation_date"],
            end_date=observed_at.date().isoformat(),
        )
        store = SignalStore(data_root / "signals.db")
        existing_ids = {
            event.signal_id
            for event in store.replay(source=SOURCE, model_version=MODEL_VERSION)
        }
        forward_start_ns = int(pd.Timestamp(contract["forward_started_at"]).value)
        new_forward = [
            event
            for event in events
            if event.ts_event > forward_start_ns and event.signal_id not in existing_ids
        ]

        last_treasury_day = date.fromisoformat(treasury_audit["last_date"])
        eligible_age_days = (target_day - last_treasury_day).days
        blockers: list[str] = []
        if repo["dirty"]:
            blockers.append("git_dirty")
        if not repo["origin_main_contains_commit"]:
            blockers.append("commit_not_on_origin_main")
        if not 0 <= eligible_age_days <= int(
            collection["treasury_max_eligible_age_calendar_days"]
        ):
            blockers.append(f"treasury_stale:{eligible_age_days}_eligible_days")
        if int(treasury_audit["maximum_calendar_gap_days"]) > int(
            collection["treasury_max_observation_gap_calendar_days"]
        ):
            blockers.append(
                "treasury_observation_gap:"
                f"{treasury_audit['maximum_calendar_gap_days']}_days"
            )
        if treasury_revisions:
            blockers.append(f"treasury_historical_revision:{len(treasury_revisions)}")
        if btc_revisions:
            blockers.append(f"btc_historical_revision:{len(btc_revisions)}")
        if not btc_contiguous:
            blockers.append("btc_hourly_gap")
        qualified = not blockers
        written = duplicates = 0
        if qualified:
            written, duplicates = store.write_many(
                events, now_ns=int(observed_at.timestamp() * 1_000_000_000)
            )
            treasury_state_path.write_text(
                json.dumps(merged_treasury, indent=2, sort_keys=True) + "\n"
            )
            btc_state_path.write_text(
                json.dumps(merged_btc, indent=2, sort_keys=True) + "\n"
            )

        record = {
            "schema_version": SCHEMA_VERSION,
            "attempt_id": attempt_id,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "collection_date": observed_at.date().isoformat(),
            "target_eligible_observation_date": target_day.isoformat(),
            "contract_path": str(contract_path),
            "contract_sha256": contract_sha256,
            "git": repo,
            "policy": contract["policy"],
            "treasury": {
                "snapshot_path": str(snapshot_path),
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "vintage_id": snapshot["vintage_id"],
                "row_count": treasury_audit["row_count"],
                "first_date": treasury_audit["first_date"],
                "last_date": treasury_audit["last_date"],
                "eligible_age_calendar_days": eligible_age_days,
                "maximum_calendar_gap_days": treasury_audit[
                    "maximum_calendar_gap_days"
                ],
                "new_observation_rows": new_treasury_rows,
                "historical_revisions": treasury_revisions,
                "forward_fill_used": False,
            },
            "btc": {
                "url": btc_url,
                "raw_path": str(btc_path),
                "raw_sha256": f"sha256:{hashlib.sha256(btc_raw).hexdigest()}",
                "closed_bar_rows": len(btc_bars),
                "first_open_time_ms": btc_bars[0]["open_time_ms"],
                "last_open_time_ms": btc_bars[-1]["open_time_ms"],
                "new_observation_rows": new_btc_rows,
                "historical_revisions": btc_revisions,
                "cumulative_contiguous": btc_contiguous,
            },
            "signals": {
                "generated_total": len(events),
                "baseline_at_or_before_forward_start": sum(
                    event.ts_event <= forward_start_ns for event in events
                ),
                "generated_after_forward_start": sum(
                    event.ts_event > forward_start_ns for event in events
                ),
                "written": written,
                "duplicates": duplicates,
                "new_forward": len(new_forward) if qualified else 0,
            },
            "new_forward_signal_ids": [event.signal_id for event in new_forward]
            if qualified
            else [],
            "blockers": sorted(blockers),
            "qualified_day": qualified,
            "boundaries": {
                "credentials_loaded": False,
                "orders_submitted": False,
                "fills_created": False,
                "source_policy_mutated": False,
                "paper_simulated_touched": False,
                "testnet_touched": False,
                "live_path_touched": False,
                "future_blind_opened": False,
            },
        }
        journal_path = journal_dir / f"{attempt_id}.json"
        if journal_path.exists():
            raise FileExistsError(f"refusing to overwrite {journal_path}")
        journal_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        records = [
            _strict_json(path.read_bytes()) for path in sorted(journal_dir.glob("*.json"))
        ]
        gate = contract["evidence_gate"]
        status = summarize_attempts(
            records,
            gate_days=int(gate["qualified_distinct_utc_collection_days"]),
            gate_signals=int(gate["new_forward_signal_events"]),
        )
        status.update(
            {
                "updated_at": record["observed_at"],
                "latest_attempt_id": attempt_id,
                "contract_sha256": contract_sha256,
                "stage": "paper_shadow",
                "policy": contract["policy"],
                "scheduler_installed": False,
                "future_blind_status": "sealed_unopened",
                "paper_simulated_status": "not_authorized",
                "testnet_status": "blocked",
                "live_status": "blocked",
            }
        )
        atomic_json(data_root / "status.json", status)
        return {"record": record, "status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--data-root", type=Path, default=Path("data/research-v16-forward")
    )
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        print(
            json.dumps(
                verify_snapshot(args.verify, args.contract), indent=2, sort_keys=True
            )
        )
        return 0
    result = collect_daily(
        repo_root=args.repo_root.resolve(),
        data_root=args.data_root,
        contract_path=args.contract,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["record"]["qualified_day"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
