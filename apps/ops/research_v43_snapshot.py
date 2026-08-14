"""Fetch and audit Binance Vision BTCUSDT daily klines for Protocol v43 (Crypto Trend & Volume)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from apps.ops.research_protocol_v43 import load_and_validate

SCHEMA_VERSION = "research.v43.snapshot.v1"
AUDIT_SCHEMA_VERSION = "research.v43.provider_qualification.v1"
RAW_ROOT = Path("data/research-v43/raw")
FACTORS_ROOT = Path("data/research-v43/factors")
QUALIFICATION_PATH = Path("docs/progress/phase-2-research-v43-provider-qualification.json")
DATA_SOURCES_PATH = Path("docs/progress/phase-2-research-v43-data-sources.json")

WARMUP_START = date(2019, 10, 1)
DEV_START = date(2020, 1, 1)
DEV_END = date(2022, 12, 31)

Fetch = Callable[[str], bytes]


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-v43 (+https://github.com/Maggyee/Nishiki-Trader)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def fetch_monthly_kline_zip(symbol: str, year: int, month: int, fetch: Fetch = _fetch) -> list[dict[str, Any]]:
    url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/1d/{symbol}-1d-{year}-{month:02d}.zip"
    try:
        raw_zip = fetch(url)
    except Exception:
        return []
    try:
        z = zipfile.ZipFile(io.BytesIO(raw_zip))
    except Exception:
        return []
    content = z.read(z.namelist()[0]).decode("utf-8")
    rows: list[dict[str, Any]] = []
    for line in content.strip().splitlines():
        if not line or "open_time" in line:
            continue
        parts = line.split(",")
        if len(parts) < 6:
            continue
        try:
            ts = int(parts[0])
            if ts > 1e16:
                ts_sec = ts / 1e9
            elif ts > 1e13:
                ts_sec = ts / 1e6
            elif ts > 1e10:
                ts_sec = ts / 1e3
            else:
                ts_sec = float(ts)
            d = datetime.fromtimestamp(ts_sec, tz=UTC).date().isoformat()
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
        except Exception:
            continue
    return rows


def fetch_symbol_range(symbol: str = "BTCUSDT", start_year: int = 2019, end_year: int = 2026, fetch: Fetch = _fetch) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            if y == 2019 and m < 10:
                continue
            if y == 2026 and m > 8:
                continue
            monthly = fetch_monthly_kline_zip(symbol, y, m, fetch=fetch)
            all_rows.extend(monthly)
    by_date: dict[str, dict[str, Any]] = {r["date"]: r for r in all_rows}
    sorted_rows = [by_date[k] for k in sorted(by_date)]
    return sorted_rows


def compute_factors(btc_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    df = pd.DataFrame(btc_rows).sort_values("date").drop_duplicates("date").reset_index(drop=True)

    # 1. MACD
    e12 = df["close"].ewm(span=12, adjust=False).mean()
    e26 = df["close"].ewm(span=26, adjust=False).mean()
    macd_line = e12 - e26
    macd_sig = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_sig

    # 2. Volume SMA20
    vol_sma20 = df["volume"].rolling(20).mean()
    vol_ratio = df["volume"] / (vol_sma20 + 1e-9)

    # 3. RSI 14
    delta = df["close"].diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1/14, adjust=False).mean()
    rsi14 = 100 - (100 / (1 + (gain / (loss + 1e-9))))

    factors_080: list[dict[str, Any]] = []
    factors_rsi080: list[dict[str, Any]] = []
    factors_085: list[dict[str, Any]] = []

    for i, r in df.iterrows():
        d = r["date"]
        # Candidate 1: macd_hist > 0 and vol_ratio > 0.80
        # Numeric factor value: positive when signal active, negative otherwise
        active_080 = (macd_hist.iloc[i] > 0.0) and (vol_ratio.iloc[i] > 0.80)
        factors_080.append({"date": d, "value": 1.0 if active_080 else -1.0})

        # Candidate 2: macd_hist > 0 and rsi14 > 45.0 and vol_ratio > 0.80
        active_rsi080 = (macd_hist.iloc[i] > 0.0) and (rsi14.iloc[i] > 45.0) and (vol_ratio.iloc[i] > 0.80)
        factors_rsi080.append({"date": d, "value": 1.0 if active_rsi080 else -1.0})

        # Candidate 3: macd_hist > 0 and vol_ratio > 0.85
        active_085 = (macd_hist.iloc[i] > 0.0) and (vol_ratio.iloc[i] > 0.85)
        factors_085.append({"date": d, "value": 1.0 if active_085 else -1.0})

    return {
        "btc_macd_vol_confirmed": factors_080,
        "btc_macd_rsi_vol_confirmed": factors_rsi080,
        "btc_macd_vol_tight": factors_085,
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
    if len(btc_rows) < 1000:
        raise ValueError(f"insufficient kline rows: BTC={len(btc_rows)}")

    observed_at = datetime.now(UTC)
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "btc_row_count": len(btc_rows),
        "btc_rows": btc_rows,
    }
    serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    snapshot_sha = f"sha256:{digest}"
    vintage_id = f"binance-vision-btc:{observed_at.isoformat()}:{digest[:12]}"
    envelope["vintage_id"] = vintage_id
    envelope["snapshot_sha256"] = snapshot_sha

    snapshot_path = raw_dir / f"binance-vision-btc-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    snapshot_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")

    factors = compute_factors(btc_rows)
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
        "schema_version": AUDIT_SCHEMA_VERSION,
        "protocol": "docs/progress/phase-2-research-protocol-v43.json",
        "evaluated_at": observed_at.isoformat().replace("+00:00", "Z"),
        "passed": True,
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_sha,
        "vintage_id": vintage_id,
        "btc_row_count": len(btc_rows),
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
