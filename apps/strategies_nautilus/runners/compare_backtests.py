"""Compare two ADR-004 backtest bundles for replay equivalence."""

from __future__ import annotations

import argparse
import filecmp
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.strategies_nautilus.result_schema import BacktestManifest

VOLATILE_MANIFEST_FIELDS = frozenset(
    {
        "run_id",
        "started_at",
        "finished_at",
        "elapsed_seconds",
    }
)

DEFAULT_PARQUET_SIDECARS = ("fills.parquet",)


@dataclass(frozen=True)
class CompareResult:
    ok: bool
    differences: tuple[str, ...]


def compare_backtest_runs(
    left_dir: Path,
    right_dir: Path,
    *,
    parquet_sidecars: tuple[str, ...] = DEFAULT_PARQUET_SIDECARS,
) -> CompareResult:
    differences: list[str] = []
    left_manifest = _load_manifest(left_dir)
    right_manifest = _load_manifest(right_dir)

    left_normalized = _normalize_manifest(left_manifest)
    right_normalized = _normalize_manifest(right_manifest)
    if left_normalized != right_normalized:
        differences.extend(_manifest_differences(left_normalized, right_normalized))

    for name in parquet_sidecars:
        left_path = left_dir / name
        right_path = right_dir / name
        if not left_path.exists():
            differences.append(f"{left_path} missing")
            continue
        if not right_path.exists():
            differences.append(f"{right_path} missing")
            continue
        if not filecmp.cmp(left_path, right_path, shallow=False):
            differences.append(f"{name} differs byte-for-byte")

    return CompareResult(ok=not differences, differences=tuple(differences))


def _load_manifest(run_dir: Path) -> BacktestManifest:
    return BacktestManifest.model_validate_json(
        (run_dir / "run_manifest.json").read_text(encoding="utf-8")
    )


def _normalize_manifest(manifest: BacktestManifest) -> dict[str, Any]:
    data = manifest.model_dump(mode="json")
    for field in VOLATILE_MANIFEST_FIELDS:
        data.pop(field, None)
    return data


def _manifest_differences(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            out.append(
                "run_manifest.json "
                f"{key} differs: {json.dumps(left.get(key), sort_keys=True)} "
                f"!= {json.dumps(right.get(key), sort_keys=True)}"
            )
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two ADR-004 backtest run directories, ignoring manifest "
            "wall-clock fields."
        ),
    )
    parser.add_argument("left_dir", type=Path)
    parser.add_argument("right_dir", type=Path)
    parser.add_argument(
        "--parquet-sidecar",
        action="append",
        default=[],
        help=(
            "Parquet sidecar to compare byte-for-byte. Defaults to fills.parquet; "
            "repeat to compare more files."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    sidecars = tuple(args.parquet_sidecar) or DEFAULT_PARQUET_SIDECARS
    try:
        result = compare_backtest_runs(
            args.left_dir,
            args.right_dir,
            parquet_sidecars=sidecars,
        )
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    if result.ok:
        print("MATCH")
        return 0
    for diff in result.differences:
        print(diff)
    return 1


__all__ = [
    "CompareResult",
    "DEFAULT_PARQUET_SIDECARS",
    "VOLATILE_MANIFEST_FIELDS",
    "compare_backtest_runs",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
