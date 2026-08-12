"""Collect one immutable qualification snapshot for Protocol v13."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v13 import DEFAULT_PROTOCOL, load_and_validate

SCHEMA_VERSION = "research.raw_snapshot.v13"
METRICS = ("AdrActCnt", "TxTfrCnt", "CapMVRVCur")
Fetch = Callable[[str], bytes]


def _contract() -> dict[str, Any]:
    load_and_validate()
    return json.loads(DEFAULT_PROTOCOL.read_text())


def request_url() -> str:
    data = _contract()["data_contract"]
    return f"{data['url']}?{urllib.parse.urlencode(data['params'])}"


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v13"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _strict_json(raw: str | bytes) -> Any:
    return json.loads(
        raw,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON {value!r}")
        ),
    )


def parse_and_audit(raw: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _strict_json(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Coin Metrics response must contain data")
    if payload.get("next_page_token") or payload.get("next_page_url"):
        raise ValueError("Protocol v13 response unexpectedly requires pagination")
    rows = payload["data"]
    seen: set[date] = set()
    first: date | None = None
    last: date | None = None
    for row in rows:
        if not isinstance(row, dict) or row.get("asset") != "btc":
            raise ValueError("Protocol v13 requires BTC rows")
        timestamp = datetime.fromisoformat(str(row.get("time")).replace("Z", "+00:00"))
        day = timestamp.date()
        if day in seen:
            raise ValueError("Protocol v13 daily rows must be unique")
        seen.add(day)
        first = day if first is None else min(first, day)
        last = day if last is None else max(last, day)
        for metric in METRICS:
            try:
                value = float(row[metric])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Protocol v13 row is missing {metric}") from exc
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"Protocol v13 {metric} must be finite and positive")
    expected_start, expected_end = date(2019, 11, 1), date(2022, 12, 31)
    expected_count = (expected_end - expected_start).days + 1
    if first != expected_start or last != expected_end or len(rows) != expected_count:
        raise ValueError("Protocol v13 daily development grid is incomplete")
    return rows, {
        "row_count": len(rows),
        "first_date": first.isoformat(),
        "last_date": last.isoformat(),
        "metrics": list(METRICS),
        "complete_daily_grid": True,
    }


def collect_snapshot(
    *, output_dir: Path, fetch: Fetch = _fetch, now: datetime | None = None
) -> tuple[Path, dict[str, Any]]:
    retrieved = (now or datetime.now(UTC)).astimezone(UTC)
    raw = fetch(request_url())
    _, audit = parse_and_audit(raw)
    validation = load_and_validate()
    core = {
        "schema_version": SCHEMA_VERSION,
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        "url": request_url(),
        "protocol_sha256": validation["protocol_sha256"],
        "payload_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "payload_raw_base64": base64.b64encode(raw).decode(),
        "audit": audit,
        "boundaries": {
            "values_reported": False,
            "signals_generated": False,
            "pnl_opened": False,
            "trading_touched": False,
        },
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    envelope = {
        **core,
        "snapshot_sha256": "sha256:" + digest,
        "vintage_id": f"coinmetrics-btc-network:{retrieved.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"btc-network-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return path, {
        "path": str(path),
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v13/raw"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(
            json.dumps(
                {"url": request_url(), "network_accessed": False, "data_written": False}, indent=2
            )
        )
        return 0
    path, result = collect_snapshot(output_dir=args.output_dir)
    print(json.dumps({**result, "path": str(path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
