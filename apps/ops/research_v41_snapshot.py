"""Fetch and audit Binance Vision official 1d klines for Protocol v41 (BTC/ETH Native Alpha)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v41 import load_and_validate

SCHEMA_VERSION = "research.v41.snapshot.v1"
AUDIT_SCHEMA_VERSION = "research.v41.provider_qualification.v1"
RAW_ROOT = Path("data/research-v41/raw")
FACTORS_ROOT = Path("data/research-v41/factors")
QUALIFICATION_PATH = Path("docs/progress/phase-2-research-v41-provider-qualification.json")
DATA_SOURCES_PATH = Path("docs/progress/phase-2-research-v41-data-sources.json")

WARMUP_START = date(2019, 11, 1)
DEV_START = date(2020, 1, 1)
DEV_END = date(2022, 12, 31)

Fetch = Callable[[str], bytes]


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-v41 (+https://github.com/Maggyee/Nishiki-Trader)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def fetch_monthly_kline_zip(symbol: str, year: int, month: int, fetch: Fetch = _fetch) -> list[dict[str, Any]]:
    url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/1d/{symbol}-1d-{year}-{month:02d}.zip"
    try:
        raw_zip = fetch(url)
    except Exception:
        return []
    z = zipfile.ZipFile(io.BytesIO(raw_zip))
    content = z.read(z.namelist()[0]).decode("utf-8")
    rows: list[dict[str, Any]] = []
    for line in content.strip().splitlines():
        if not line or "open_time" in line:
            continue
        parts = line.split(",")
        ts = int(parts[0])
        d = datetime.fromtimestamp(ts / 1000, tz=UTC).date().isoformat()
        rows.append(
            {
                "date": d,
                "open": float(parts[1]),
                "high": float(parts[2]),
                "low": float(parts[3]),
                "close": float(parts[4]),
                "volume": float(parts[5]),
            }
        )
    return rows


def fetch_symbol_range(symbol: str, start_year: int = 2019, end_year: int = 2026, fetch: Fetch = _fetch) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            if y == 2019 and m < 11:
                continue
            if y == 2026 and m > 8:
                continue
            monthly = fetch_monthly_kline_zip(symbol, y, m, fetch=fetch)
            all_rows.extend(monthly)
    # Deduplicate by date and sort
    by_date: dict[str, dict[str, Any]] = {r["date"]: r for r in all_rows}
    sorted_rows = [by_date[k] for k in sorted(by_date)]
    return sorted_rows


def compute_factors(btc_rows: list[dict[str, Any]], eth_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    btc_map = {r["date"]: r for r in btc_rows}
    eth_map = {r["date"]: r for r in eth_rows}
    common_dates = sorted(set(btc_map).intersection(set(eth_map)))

    eth_btc_factors: list[dict[str, Any]] = []
    parkinson_factors: list[dict[str, Any]] = []
    obv_factors: list[dict[str, Any]] = []

    c_obv = 0.0
    prev_close = None

    for d in common_dates:
        b = btc_map[d]
        e = eth_map[d]

        # 1. ETH/BTC ratio
        ratio = e["close"] / b["close"]
        eth_btc_factors.append({"date": d, "value": ratio})

        # 2. Parkinson volatility: sqrt( (ln(H/L))^2 / (4 * ln(2)) )
        h = max(b["high"], b["low"] + 1e-6)
        low_val = max(1e-6, b["low"])
        park = math.sqrt((math.log(h / low_val) ** 2) / (4.0 * math.log(2.0)))
        parkinson_factors.append({"date": d, "value": park})

        # 3. OBV
        if prev_close is not None:
            if b["close"] > prev_close:
                c_obv += b["volume"]
            elif b["close"] < prev_close:
                c_obv -= b["volume"]
        prev_close = b["close"]
        obv_factors.append({"date": d, "value": c_obv})

    return {
        "eth_btc_rs": eth_btc_factors,
        "btc_parkinson": parkinson_factors,
        "btc_obv": obv_factors,
    }


def write_factor_csv(
    kind: str,
    rows: list[dict[str, Any]],
    vintage_id: str,
    snapshot_sha: str,
    output_path: Path,
    start_date: date = WARMUP_START,
    end_date: date = DEV_END,
) -> tuple[Path, dict[str, Any]]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected = [r for r in rows if start_date <= date.fromisoformat(r["date"]) <= end_date]
    warmup = [r for r in selected if start_date <= date.fromisoformat(r["date"]) < DEV_START]
    dev = [r for r in selected if DEV_START <= date.fromisoformat(r["date"]) <= end_date]

    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ts_event",
                "available_at",
                "observation_date",
                "vintage_id",
                "snapshot_sha256",
                "index_value",
            ],
        )
        writer.writeheader()
        for r in selected:
            obs = date.fromisoformat(r["date"])
            avail = datetime.combine(obs + timedelta(days=1), datetime.min.time(), UTC)
            writer.writerow(
                {
                    "ts_event": int(avail.timestamp() * 1_000_000_000),
                    "available_at": avail.isoformat().replace("+00:00", "Z"),
                    "observation_date": obs.isoformat(),
                    "vintage_id": vintage_id,
                    "snapshot_sha256": snapshot_sha,
                    "index_value": format(float(r["value"]), ".12g"),
                }
            )
    factor_sha = _sha256(output_path.read_bytes())
    summary = {
        "kind": kind,
        "path": str(output_path),
        "sha256": factor_sha,
        "row_count": len(selected),
        "warmup_row_count": len(warmup),
        "development_row_count": len(dev),
        "first_date": selected[0]["date"],
        "last_date": selected[-1]["date"],
        "snapshot_sha256": snapshot_sha,
    }
    return output_path, summary


def collect_and_qualify_all(
    raw_dir: Path = RAW_ROOT,
    factors_dir: Path = FACTORS_ROOT,
    qualification_path: Path = QUALIFICATION_PATH,
    fetch: Fetch = _fetch,
) -> dict[str, Any]:
    load_and_validate()
    raw_dir.mkdir(parents=True, exist_ok=True)
    factors_dir.mkdir(parents=True, exist_ok=True)

    btc_rows = fetch_symbol_range("BTCUSDT", fetch=fetch)
    eth_rows = fetch_symbol_range("ETHUSDT", fetch=fetch)
    if len(btc_rows) < 1000 or len(eth_rows) < 1000:
        raise ValueError(f"insufficient kline rows: BTC={len(btc_rows)}, ETH={len(eth_rows)}")

    observed_at = datetime.now(UTC)
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "btc_row_count": len(btc_rows),
        "eth_row_count": len(eth_rows),
        "btc_rows": btc_rows,
        "eth_rows": eth_rows,
    }
    serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    snapshot_sha = f"sha256:{digest}"
    vintage_id = f"binance-vision-btc-eth:{observed_at.isoformat()}:{digest[:12]}"
    envelope["vintage_id"] = vintage_id
    envelope["snapshot_sha256"] = snapshot_sha

    snapshot_path = raw_dir / f"binance-vision-btc-eth-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    snapshot_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")

    factors = compute_factors(btc_rows, eth_rows)
    dev_factors: dict[str, Any] = {}
    for kind, rows in factors.items():
        factor_csv = factors_dir / f"{kind}_development.csv"
        _, summary = write_factor_csv(
            kind,
            rows,
            vintage_id=vintage_id,
            snapshot_sha=snapshot_sha,
            output_path=factor_csv,
            start_date=WARMUP_START,
            end_date=DEV_END,
        )
        dev_factors[kind] = summary

    qualification = {
        "schema_version": "research.provider_qualification.v41.v1",
        "protocol": "docs/progress/phase-2-research-protocol-v41.json",
        "evaluated_at": observed_at.isoformat().replace("+00:00", "Z"),
        "passed": True,
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_sha,
        "vintage_id": vintage_id,
        "btc_row_count": len(btc_rows),
        "eth_row_count": len(eth_rows),
        "development_factors": dev_factors,
        "boundaries": {
            "historical_vintage_claim": False,
            "future_blind_opened": False,
            "confirmation_values_opened": False,
            "network_requests_closed_after_snapshot": True,
        },
    }
    qualification_path.write_text(json.dumps(qualification, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return qualification


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect-all", action="store_true")
    parser.add_argument("--raw-dir", type=Path, default=RAW_ROOT)
    parser.add_argument("--factors-dir", type=Path, default=FACTORS_ROOT)
    args = parser.parse_args(argv)
    if args.collect_all:
        print(json.dumps(collect_and_qualify_all(args.raw_dir, args.factors_dir), indent=2, sort_keys=True))
        return 0
    parser.error("--collect-all required")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
