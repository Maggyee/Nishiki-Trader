from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from apps.ops.research_v5_daily import run_daily_collection


def test_daily_dry_run_is_commit_locked_and_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = "a" * 40

    def check_output(command: list[str], **_: object) -> str:
        if command[1:] == ["rev-parse", "HEAD"]:
            return f"{commit}\n"
        if command[1:] == ["status", "--porcelain", "--untracked-files=no"]:
            return ""
        raise AssertionError(command)

    monkeypatch.setattr("apps.ops.research_v5_daily.subprocess.check_output", check_output)

    report = run_daily_collection(
        date(2026, 7, 16),
        data_root=tmp_path / "data",
        expected_git_commit=commit,
        repo_root=tmp_path,
        dry_run=True,
    )

    assert report["git_commit"] == commit
    assert len(report["plans"]) == 4
    assert report["network_accessed"] is False
    assert report["data_written"] is False
    assert report["signals_generated"] is False
    assert report["pnl_computed"] is False
    assert not (tmp_path / "data").exists()


def test_daily_rejects_commit_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "apps.ops.research_v5_daily.subprocess.check_output",
        lambda *_args, **_kwargs: f"{'b' * 40}\n",
    )

    with pytest.raises(ValueError, match="differs from locked commit"):
        run_daily_collection(
            date(2026, 7, 16),
            data_root=tmp_path / "data",
            expected_git_commit="a" * 40,
            repo_root=tmp_path,
            dry_run=True,
        )


def test_daily_rejects_tracked_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = "a" * 40
    responses = iter((f"{commit}\n", " M apps/ops/research_v5_daily.py\n"))
    monkeypatch.setattr(
        "apps.ops.research_v5_daily.subprocess.check_output",
        lambda *_args, **_kwargs: next(responses),
    )

    with pytest.raises(ValueError, match="tracked working-tree changes"):
        run_daily_collection(
            date(2026, 7, 16),
            data_root=tmp_path / "data",
            expected_git_commit=commit,
            repo_root=tmp_path,
            dry_run=True,
        )
