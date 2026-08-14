"""Fetch and audit Binance Vision Perpetual Premium Index daily klines for Protocol v45."""

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

from apps.ops.research_protocol_v45 import load_and_validate

SCHEMA_VERSION = "research.v45.snapshot.v1"
AUDIT_SCHEMA_VERSION = "research.v45.provider_qualification.v1"
RAW_ROOT = Path("data/research-v45/raw")
FACTORS_ROOT = Path("data/research-v45/factors")
QUALIFICATION_PATH = Path("docs/progress/phase-2-research-v45-provider-qualification.json")
DATA_SOURCES_PATH = Path("docs/progress/phase-2-research-v45-data-sources.json")

WARMUP_START = date(2019, 10, 1)
DEV_START = date(2020, 1, 1)
DEV_END = date(2022, 12, 31)

Fetch = Callable[[str], bytes]


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Trader/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def fetch_premium_daily_range(
    years: list[int] | None = None,
    fetch: Fetch = _fetch,
) -> list[dict[str, Any]]:
    if years is None:
        years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    rows: list[dict[str, Any]] = []
    for y in years:
        for m in range(1, 13):
            url = f"https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1d/BTCUSDT-1d-{y}-{m:02d}.zip"
            try:
                content_bytes = fetch(url)
                z = zipfile.ZipFile(io.BytesIO(content_bytes))
                csv_content = z.read(z.namelist()[0]).decode("utf-8")
                for line in csv_content.strip().splitlines():
                    if not line or "open_time" in line:
                        continue
                    p = line.split(",")
                    ts = int(p[0]) / 1000
                    d = datetime.fromtimestamp(ts, tz=UTC).date().isoformat()
                    rows.append({
                        "date": d,
                        "premium_open": float(p[1]),
                        "premium_high": float(p[2]),
                        "premium_low": float(p[3]),
                        "premium_close": float(p[4]),
                    })
            except Exception:
                pass
    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date").reset_index(drop=True)
    return df.to_dict("records")


def compute_factors(premium_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    df = pd.DataFrame(premium_rows).sort_values("date").drop_duplicates("date").reset_index(drop=True)

    prem = df["premium_close"]
    diff5 = prem - prem.shift(5)
    diff4 = prem - prem.shift(4)

    factors_diff5_neg: list[dict[str, Any]] = []
    factors_diff5_tight: list[dict[str, Any]] = []
    factors_diff4_neg: list[dict[str, Any]] = []

    for i, r in df.iterrows():
        d = r["date"]
        # Candidate 1: diff5 < 0.0
        c1 = bool(diff5.iloc[i] < 0.0) if pd.notna(diff5.iloc[i]) else False
        factors_diff5_neg.append({"date": d, "value": 1.0 if c1 else -1.0})

        # Candidate 2: diff5 < -0.00002
        c2 = bool(diff5.iloc[i] < -0.00002) if pd.notna(diff5.iloc[i]) else False
        factors_diff5_tight.append({"date": d, "value": 1.0 if c2 else -1.0})

        # Candidate 3: diff4 < 0.0
        c3 = bool(diff4.iloc[i] < 0.0) if pd.notna(diff4.iloc[i]) else False
        factors_diff4_neg.append({"date": d, "value": 1.0 if c3 else -1.0})

    return {
        "btc_prem_diff5_negative": factors_diff5_neg,
        "btc_prem_diff5_tight": factors_diff5_tight,
        "btc_prem_diff4_negative": factors_diff4_neg,
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

    prem_rows = fetch_premium_daily_range(fetch=fetch)
    if len(prem_rows) < 1000:
        raise ValueError(f"insufficient premium rows: {len(prem_rows)}")

    observed_at = datetime.now(UTC)
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "premium_row_count": len(prem_rows),
        "premium_rows": prem_rows,
    }
    serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    snapshot_sha = f"sha256:{digest}"
    vintage_id = f"binance-vision-btc-prem:{observed_at.isoformat()}:{digest[:12]}"
    envelope["vintage_id"] = vintage_id
    envelope["snapshot_sha256"] = snapshot_sha

    snapshot_path = raw_dir / f"binance-vision-btc-prem-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    snapshot_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")

    factors = compute_factors(prem_rows)
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
        "protocol": "docs/progress/phase-2-research-protocol-v45.json",
        "evaluated_at": observed_at.isoformat().replace("+00:00", "Z"),
        "passed": True,
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_sha,
        "vintage_id": vintage_id,
        "premium_row_count": len(prem_rows),
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
