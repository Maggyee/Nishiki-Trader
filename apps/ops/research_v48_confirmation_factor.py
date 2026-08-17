"""Generate confirmation factor CSV for Protocol v48 candidate."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from apps.ops.research_v48_confirmation import load_and_validate_confirmation
from apps.ops.research_v48_snapshot import (
    QUALIFICATION_PATH,
    compute_factors,
    write_factor_csv,
)

CONF_START = date(2023, 1, 1)
CONF_END = date(2025, 12, 31)
FACTORS_ROOT = Path("data/research-v48/factors")


def generate_confirmation_factor() -> Path:
    load_and_validate_confirmation()
    qual = json.loads(QUALIFICATION_PATH.read_text())
    snapshot_path = Path(qual["snapshot_path"])
    envelope = json.loads(snapshot_path.read_text())
    basis_rows = envelope["basis_rows"]

    factors = compute_factors(basis_rows)
    kind = "btc_basis_below_ma10"
    output_path = FACTORS_ROOT / f"{kind}_confirmation.csv"
    write_factor_csv(
        kind,
        factors[kind],
        vintage_id=qual["vintage_id"],
        snapshot_sha=qual["snapshot_sha256"],
        output_path=output_path,
        start_date=CONF_START,
        end_date=CONF_END,
    )
    print(f"wrote confirmation factor CSV to {output_path}")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    generate_confirmation_factor()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
