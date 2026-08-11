"""Collect qualification-only immutable Coin Metrics Protocol v10 snapshots."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v10 import DEFAULT_PROTOCOL, KINDS, load_and_validate

SCHEMA_VERSION = "research.raw_snapshot.v10"
Fetch = Callable[[str], bytes]


def _protocol() -> dict[str, Any]:
    load_and_validate()
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    return payload


def _request(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unsupported Protocol v10 kind {kind!r}")
    return next(
        row for row in _protocol()["provider_qualification"]["requests"] if row["kind"] == kind
    )


def _url(spec: dict[str, Any]) -> str:
    return f"{spec['url']}?{urllib.parse.urlencode(spec['params'])}"


def _boundaries() -> dict[str, bool]:
    return {
        "credentials_loaded": False,
        "values_reported": False,
        "signals_generated": False,
        "pnl_calculated": False,
        "source_policy_mutated": False,
        "testnet_resumed": False,
        "live_path_touched": False,
    }


def request_plan(kind: str) -> dict[str, Any]:
    spec = _request(kind)
    return {
        "schema_version": "research.snapshot.request_plan.v10",
        "kind": kind,
        "url": _url(spec),
        "network_accessed": False,
        "data_written": False,
        "qualification_only": True,
        "boundaries": _boundaries(),
    }


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v10"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _strict_json(raw: bytes | str) -> Any:
    return json.loads(
        raw,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {value!r}")
        ),
    )


def _expected(kind: str) -> tuple[set[str], str]:
    if kind == "hashrate":
        return {"btc"}, "HashRate"
    if kind == "stablecoin_supply":
        return {"usdt", "usdc"}, "SplyCur"
    return {"btc"}, "FeeTotNtv"


def parse_and_audit(kind: str, raw: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _strict_json(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Coin Metrics response must contain a data list")
    if payload.get("next_page_token") or payload.get("next_page_url"):
        raise ValueError("locked Coin Metrics request unexpectedly requires pagination")
    rows = payload["data"]
    expected_assets, metric = _expected(kind)
    seen_assets: set[str] = set()
    seen: set[tuple[str, str]] = set()
    first_time: str | None = None
    last_time: str | None = None
    status_time_rows = 0
    eligible_status_time_rows = 0
    counts: dict[str, int] = {asset: 0 for asset in expected_assets}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Coin Metrics row {index} must be an object")
        asset = str(row.get("asset"))
        if asset not in expected_assets:
            raise ValueError(f"unexpected Coin Metrics asset {asset!r}")
        timestamp = str(row.get("time"))
        try:
            observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid Coin Metrics time {timestamp!r}") from exc
        if observed.tzinfo is None:
            raise ValueError("Coin Metrics time must include a timezone")
        key = (asset, timestamp)
        if key in seen:
            raise ValueError("Coin Metrics asset/time rows must be unique")
        seen.add(key)
        seen_assets.add(asset)
        counts[asset] += 1
        try:
            value = float(row[metric])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Coin Metrics row is missing numeric {metric}") from exc
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"Coin Metrics {metric} must be finite and non-negative")
        status_time = row.get(f"{metric}-status-time")
        if status_time is not None:
            status_time_rows += 1
            reviewed = datetime.fromisoformat(str(status_time).replace("Z", "+00:00"))
            if reviewed.tzinfo is None:
                raise ValueError("Coin Metrics status-time must include a timezone")
            decision_deadline = observed.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=2)
            if reviewed <= decision_deadline:
                eligible_status_time_rows += 1
        first_time = timestamp if first_time is None or timestamp < first_time else first_time
        last_time = timestamp if last_time is None or timestamp > last_time else last_time
    if seen_assets != expected_assets:
        raise ValueError(f"Coin Metrics response assets {seen_assets!r} != {expected_assets!r}")
    if any(count < 1000 for count in counts.values()):
        raise ValueError(f"Coin Metrics development coverage is incomplete: {counts}")
    audit = {
        "row_count": len(rows),
        "asset_row_counts": counts,
        "first_time": first_time,
        "last_time": last_time,
        "metric": metric,
        "status_time_row_count": status_time_rows,
        "eligible_status_time_row_count": eligible_status_time_rows,
        "all_rows_point_in_time_eligible": status_time_rows == len(rows)
        and eligible_status_time_rows == len(rows),
        "development_coverage": True,
    }
    return rows, audit


def collect_snapshot(
    kind: str,
    *,
    output_dir: Path,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    spec = _request(kind)
    retrieved = (now or datetime.now(UTC)).astimezone(UTC)
    raw = fetch(_url(spec))
    if not raw:
        raise ValueError(f"{kind} returned an empty response")
    _, audit = parse_and_audit(kind, raw)
    core = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        "protocol_path": str(DEFAULT_PROTOCOL),
        "protocol_sha256": load_and_validate()["protocol_sha256"],
        "url": _url(spec),
        "payload_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
        "audit": audit,
        "boundaries": _boundaries(),
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    envelope = {
        **core,
        "snapshot_sha256": f"sha256:{digest}",
        "vintage_id": f"coinmetrics-{kind}:{retrieved.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{kind}-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = _strict_json(path.read_bytes())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v10 snapshot schema")
    kind = str(envelope.get("kind"))
    spec = _request(kind)
    if envelope.get("url") != _url(spec):
        raise ValueError("Protocol v10 snapshot request identity drifted")
    if envelope.get("boundaries") != _boundaries():
        raise ValueError("Protocol v10 snapshot boundaries are unsafe")
    if envelope.get("protocol_sha256") != load_and_validate()["protocol_sha256"]:
        raise ValueError("Protocol v10 protocol fingerprint mismatch")
    raw = base64.b64decode(str(envelope.get("payload_raw_base64")), validate=True)
    if envelope.get("payload_sha256") != f"sha256:{hashlib.sha256(raw).hexdigest()}":
        raise ValueError("Protocol v10 raw payload fingerprint mismatch")
    _, audit = parse_and_audit(kind, raw)
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v10 snapshot audit mismatch")
    core = {
        key: value
        for key, value in envelope.items()
        if key not in {"snapshot_sha256", "vintage_id"}
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if envelope.get("snapshot_sha256") != f"sha256:{digest}":
        raise ValueError("Protocol v10 snapshot fingerprint mismatch")
    if not str(envelope.get("vintage_id", "")).endswith(digest[:12]):
        raise ValueError("Protocol v10 snapshot vintage mismatch")
    return {
        "schema_version": SCHEMA_VERSION,
        "path": str(path),
        "kind": kind,
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v10/raw"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        print(json.dumps(verify_snapshot(args.verify), indent=2, sort_keys=True))
        return 0
    if args.kind is None:
        parser.error("--kind is required unless --verify is used")
    if args.dry_run:
        print(json.dumps(request_plan(args.kind), indent=2, sort_keys=True))
        return 0
    path, result = collect_snapshot(args.kind, output_dir=args.output_dir)
    print(json.dumps({**result, "path": str(path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
