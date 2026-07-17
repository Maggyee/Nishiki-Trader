"""Run one credential-free, idempotent daily Protocol v5 collection batch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from apps.ops.research_v5_snapshot import ASSETS, collect_snapshot, request_plan


def _clean_locked_commit(expected: str, repo_root: Path) -> str:
    if len(expected) != 40 or any(char not in "0123456789abcdef" for char in expected):
        raise ValueError("--expected-git-commit must be a 40-character lowercase SHA")
    marker = repo_root / ".collector-git-sha"
    dirty = ""
    if (repo_root / ".git").exists():
        actual = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo_root,
            text=True,
        ).strip()
    elif marker.is_file():
        actual = marker.read_text(encoding="ascii").strip()
        if os.environ.get("TRADER_GIT_SHA") != actual:
            raise ValueError("collector image environment differs from its build marker")
    else:
        raise ValueError("collector requires a git checkout or immutable build marker")
    if actual != expected:
        raise ValueError(f"collector commit {actual} differs from locked commit {expected}")
    if dirty:
        raise ValueError("collector checkout has tracked working-tree changes")
    return actual


def run_daily_collection(
    data_day: date,
    *,
    data_root: Path,
    expected_git_commit: str,
    repo_root: Path,
    dry_run: bool = False,
) -> dict:
    commit = _clean_locked_commit(expected_git_commit, repo_root)
    if dry_run:
        return {
            "schema_version": "research.v5.daily_collection.v1",
            "data_date": data_day.isoformat(),
            "git_commit": commit,
            "plans": [
                request_plan(kind, asset, [data_day])
                for kind in ("delivery_curve", "bvol")
                for asset in ASSETS
            ],
            "network_accessed": False,
            "data_written": False,
            "signals_generated": False,
            "pnl_computed": False,
        }
    results = [
        collect_snapshot(
            kind,
            asset,
            data_day,
            raw_root=data_root / "raw",
            normalized_root=data_root / "normalized",
        )
        for kind in ("delivery_curve", "bvol")
        for asset in ASSETS
    ]
    conflicts = [result for result in results if result.get("result_comparison_blocked")]
    return {
        "schema_version": "research.v5.daily_collection.v1",
        "data_date": data_day.isoformat(),
        "git_commit": commit,
        "snapshots": results,
        "vintage_conflict_count": len(conflicts),
        "comparison_allowed": not conflicts,
        "signals_generated": False,
        "pnl_computed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--expected-git-commit", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        data_day = (
            date.fromisoformat(args.date)
            if args.date
            else datetime.now(UTC).date() - timedelta(days=1)
        )
        report = run_daily_collection(
            data_day,
            data_root=args.data_root,
            expected_git_commit=args.expected_git_commit,
            repo_root=args.repo_root,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
