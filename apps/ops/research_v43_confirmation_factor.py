"""Extract and audit 2023-2025 confirmation factor CSV for Protocol v43 (BTC MACD Volume Confirmed)."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from apps.ops.research_v43_confirmation import load_and_validate
from apps.ops.research_v43_snapshot import (
    FACTORS_ROOT,
    RAW_ROOT,
    compute_factors,
    write_factor_csv,
)

CONFIRMATION_START = date(2023, 1, 1)
CONFIRMATION_END = date(2025, 12, 31)
CONFIRMATION_WARMUP_START = date(2022, 10, 1)


def generate_confirmation_factors(
    raw_dir: Path = RAW_ROOT,
    factors_dir: Path = FACTORS_ROOT,
) -> tuple[Path, dict[str, Any]]:
    load_and_validate()
    matches = sorted(raw_dir.glob("binance-vision-btc-*.json"))
    if not matches:
        raise ValueError(f"no raw snapshot found in {raw_dir}")
    snapshot_path = matches[-1]
    envelope = json.loads(snapshot_path.read_text())
    btc_rows = envelope["btc_rows"]
    factors = compute_factors(btc_rows)

    factor_csv = factors_dir / "btc_macd_vol_confirmed_confirmation.csv"
    out_path, summary = write_factor_csv(
        "btc_macd_vol_confirmed",
        factors["btc_macd_vol_confirmed"],
        vintage_id=envelope["vintage_id"],
        snapshot_sha=envelope["snapshot_sha256"],
        output_path=factor_csv,
        start_date=CONFIRMATION_WARMUP_START,
        end_date=CONFIRMATION_END,
    )
    audit = {
        "schema_version": "research.v43.confirmation_data_sources.v1",
        "factor_summary": summary,
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": envelope["snapshot_sha256"],
    }
    audit_file = Path("docs/progress/phase-2-research-v43-confirmation-data-sources.json")
    audit_file.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    return out_path, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_ROOT)
    parser.add_argument("--factors-dir", type=Path, default=FACTORS_ROOT)
    args = parser.parse_args(argv)
    path, summary = generate_confirmation_factors(args.raw_dir, args.factors_dir)
    print(f"wrote confirmation factors to {path}: {summary['row_count']} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
