from __future__ import annotations

from pathlib import Path

from apps.ops.research_portfolio_monitor import (
    CANDIDATE_SPECS,
    compute_portfolio_metrics,
    generate_portfolio_markdown_report,
    load_candidate_data,
    run_monitor,
)


def test_candidate_specs_roster() -> None:
    assert len(CANDIDATE_SPECS) == 10
    protocols = {c["protocol"] for c in CANDIDATE_SPECS}
    assert protocols == {"v8", "v16", "v18", "v22", "v34", "v36", "v40", "v42", "v46", "v48"}


def test_load_candidate_data_from_repo(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    candidates = load_candidate_data(repo_root)
    assert len(candidates) == 10
    v40 = next(c for c in candidates if c["protocol"] == "v40")
    assert v40["threshold_met"] is True
    assert v40["qualified_days"] == 7
    assert v40["signals_count"] == 20


def test_compute_portfolio_metrics_and_exposure() -> None:
    repo_root = Path.cwd()
    candidates = load_candidate_data(repo_root)
    metrics = compute_portfolio_metrics(candidates)
    assert metrics["active_series_count"] >= 5
    assert "correlation_matrix" in metrics
    assert "overlap_matrix" in metrics
    assert "portfolio_exposure_stats" in metrics
    assert metrics["portfolio_exposure_stats"]["max_concurrent_active_strategies"] >= 1


def test_generate_portfolio_markdown_report() -> None:
    repo_root = Path.cwd()
    candidates = load_candidate_data(repo_root)
    metrics = compute_portfolio_metrics(candidates)
    md = generate_portfolio_markdown_report(candidates, metrics)
    assert "# Phase 5 Multi-Candidate Forward Paper-Shadow Portfolio Report" in md
    assert "## 1. Candidate Roster & Progress" in md
    assert "## 2. Cross-Strategy Correlation Matrix" in md


def test_run_monitor_end_to_end(tmp_path: Path) -> None:
    json_path = tmp_path / "portfolio_status.json"
    md_path = tmp_path / "portfolio_report.md"
    payload = run_monitor(
        repo_root=Path.cwd(),
        output_json_path=json_path,
        output_md_path=md_path,
    )
    assert payload["schema_version"] == "research.portfolio_shadow_monitor.v1"
    assert json_path.exists()
    assert md_path.exists()
