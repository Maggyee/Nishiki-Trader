"""Apply frozen Protocol v22 gates to duplicate development bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v22 import (
    IDENTITIES,
    load_and_validate,
    load_execution_amendment,
)
from apps.ops.research_v13_review import build_standard_review

SCHEMA_VERSION = "research.v22.development_results.v1"
PROVIDER_QUALIFICATION = Path("docs/progress/phase-2-research-v22-provider-qualification.json")


def load_provider_qualification(
    path: Path = PROVIDER_QUALIFICATION,
) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != "research.v22.provider_qualification.v1":
        raise ValueError("Protocol v22 provider qualification schema drifted")
    validation = load_and_validate()
    if payload.get("protocol_sha256") != validation["protocol_sha256"]:
        raise ValueError("Protocol v22 provider qualification fingerprint drifted")
    if payload.get("provider_contract_sha256") != validation["provider_contract_sha256"]:
        raise ValueError("Protocol v22 provider contract fingerprint drifted")
    qualified = payload.get("qualified_candidates")
    if not isinstance(qualified, list) or not qualified:
        raise ValueError("Protocol v22 has no provider-qualified candidate")
    return payload


def build_review(
    candidate_specs: list[tuple[str, Path]],
    *,
    downtime_results: dict[str, Any],
    gap_detail: dict[str, Any],
    gap_detail_bytes: bytes,
) -> dict[str, Any]:
    qualification = load_provider_qualification()
    amendment = load_execution_amendment()
    qualified = set(qualification["qualified_candidates"])
    if any(key not in qualified for key, _ in candidate_specs):
        raise ValueError("Protocol v22 review includes a provider-rejected candidate")
    result = build_standard_review(
        candidate_specs,
        identities=IDENTITIES,
        load_protocol=load_and_validate,
        protocol_version="v22",
        schema_version=SCHEMA_VERSION,
        downtime_results=downtime_results,
        gap_detail=gap_detail,
        gap_detail_bytes=gap_detail_bytes,
    )
    result["provider_qualification"] = {
        "qualified_candidates": qualification["qualified_candidates"],
        "rejected_candidates": qualification["rejected_candidates"],
        "historical_vintage_claim": False,
    }
    result["execution_amendment"] = amendment
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
