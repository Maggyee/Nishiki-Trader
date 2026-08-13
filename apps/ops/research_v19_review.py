"""Apply the frozen Protocol v19 gates to provider-qualified bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v19 import IDENTITIES, load_and_validate
from apps.ops.research_v13_review import (
    _classification as _classification,
)
from apps.ops.research_v13_review import build_standard_review

SCHEMA_VERSION = "research.v19.development_results.v1"
PROVIDER_QUALIFICATION = Path(
    "docs/progress/phase-2-research-v19-provider-qualification.json"
)
PROVIDER_REJECTED = {
    "china_vol_relief": {
        "classification": "reject_candidate",
        "failure_reasons": ["provider_development_rows_533_below_700"],
        "development_row_count": 533,
    }
}


def load_provider_qualification(
    path: Path = PROVIDER_QUALIFICATION,
) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != "research.v19.provider_qualification.v1":
        raise ValueError("Protocol v19 provider qualification schema drifted")
    if payload.get("protocol_sha256") != load_and_validate()["protocol_sha256"]:
        raise ValueError("Protocol v19 provider qualification fingerprint drifted")
    if payload.get("classification") != "provider_partially_qualified":
        raise ValueError("Protocol v19 provider qualification status drifted")
    if payload.get("development_eligible_candidates") != [
        "russell_vol_relief",
        "dow_vol_relief",
    ]:
        raise ValueError("Protocol v19 development-eligible candidates drifted")
    rejected = payload.get("provider_rejected_candidates")
    if rejected != {
        "china_vol_relief": {
            "reason": "development_rows_533_below_locked_minimum_700",
            "request_openings": 1,
            "retry_allowed": False,
        }
    }:
        raise ValueError("Protocol v19 provider rejection evidence drifted")
    if payload.get("confirmation_status") != "sealed_unopened" or payload.get(
        "future_blind_status"
    ) != "sealed_unopened":
        raise ValueError("Protocol v19 sealed partitions drifted")
    boundaries = payload.get("boundaries", {})
    if boundaries.get("signals_generated") is not False or boundaries.get("pnl_opened") is not False:
        raise ValueError("Protocol v19 provider qualification crossed strategy boundaries")
    return payload


def build_review(
    candidate_specs: list[tuple[str, Path]],
    *,
    downtime_results: dict[str, Any],
    gap_detail: dict[str, Any],
    gap_detail_bytes: bytes,
) -> dict[str, Any]:
    qualification = load_provider_qualification()
    eligible = {
        key: IDENTITIES[key]
        for key in qualification["development_eligible_candidates"]
    }
    result = build_standard_review(
        candidate_specs,
        identities=eligible,
        load_protocol=load_and_validate,
        protocol_version="v19",
        schema_version=SCHEMA_VERSION,
        downtime_results=downtime_results,
        gap_detail=gap_detail,
        gap_detail_bytes=gap_detail_bytes,
    )
    for key, provider_result in PROVIDER_REJECTED.items():
        source, model_version = IDENTITIES[key]
        result["candidates"].append(
            {
                "key": key,
                "source": source,
                "model_version": model_version,
                "classification": provider_result["classification"],
                "failure_reasons": provider_result["failure_reasons"],
                "development_row_count": provider_result["development_row_count"],
                "performance_pass": False,
                "evidence_pass": False,
                "signal_count": 0,
                "duplicate_replays": 0,
            }
        )
    result["provider_qualification"] = {
        "classification": qualification["classification"],
        "development_eligible_candidates": qualification[
            "development_eligible_candidates"
        ],
        "provider_rejected_candidates": qualification[
            "provider_rejected_candidates"
        ],
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", required=True, help="key=bundle")
    parser.add_argument("--downtime-results", type=Path, required=True)
    parser.add_argument("--gap-detail", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    specs: list[tuple[str, Path]] = []
    for value in args.candidate:
        if "=" not in value:
            parser.error("--candidate must use key=bundle")
        key, path = value.split("=", 1)
        specs.append((key, Path(path)))
    gap_bytes = args.gap_detail.read_bytes()
    result = build_review(
        specs,
        downtime_results=json.loads(args.downtime_results.read_text()),
        gap_detail=json.loads(gap_bytes),
        gap_detail_bytes=gap_bytes,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
