"""Run a frozen research contract.

    uv run python -m apps.research.protocol fetch <contract.json>
    uv run python -m apps.research.protocol run <contract.json> --stage development

Results are written once to ``docs/research/results/`` and the family registry
outcome is updated. Confirmation runs only for development passes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from apps.research import data, gates, replay

RESULTS_DIR = Path("docs/research/results")
REGISTRY_PATH = Path("docs/research/family-registry.json")
STAGES = ("development", "confirmation")


def load_contract(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _datasets(contract: dict) -> list[str]:
    spec = contract["data"]
    return list(spec.get("datasets") or [spec["dataset"]])


def fetch_contract(contract: dict, *, root: Path = data.DATA_ROOT) -> dict[str, int]:
    spec = contract["data"]
    last_day = pd.Period(spec["fetch_end_month"], freq="M").end_time.date().isoformat()
    counts: dict[str, int] = {}
    for dataset in _datasets(contract):
        daily = data.DATASETS[dataset][2] == "daily"
        start = spec["metrics_fetch_start_date"] if daily else spec["fetch_start_month"]
        end = last_day if daily else spec["fetch_end_month"]
        for symbol in spec["symbols"]:
            entries = data.fetch(dataset, symbol, start, end, root=root)
            counts[f"{dataset}/{symbol}"] = sum(1 for sha in entries.values() if sha)
    return counts


def _manifest_digest(root: Path, contract: dict) -> str:
    manifest = json.loads((root / "manifest.json").read_text())
    prefixes = [
        "raw/" + data.DATASETS[ds][0].format(symbol=s)
        for ds in _datasets(contract)
        for s in contract["data"]["symbols"]
    ]
    used = {k: v for k, v in manifest.items() if any(k.startswith(p + "/") for p in prefixes)}
    return hashlib.sha256(json.dumps(used, sort_keys=True).encode()).hexdigest()


def run_stage(
    contract_path: Path,
    stage: str,
    *,
    root: Path = data.DATA_ROOT,
    results_dir: Path = RESULTS_DIR,
    registry_path: Path = REGISTRY_PATH,
) -> dict:
    contract, contract_sha = load_contract(contract_path)
    tag = f"v{contract['protocol']}"
    out_path = results_dir / f"{tag}-{stage}.json"
    if out_path.exists():
        raise FileExistsError(f"{out_path} exists; results are immutable")
    eligible = set(contract["candidates"])
    if stage == "confirmation":
        development = json.loads((results_dir / f"{tag}-development.json").read_text())
        if development["contract_sha256"] != contract_sha:
            raise ValueError("contract changed since development")
        eligible = {k for k, v in development["candidates"].items() if v["gates"]["pass"]}

    module = importlib.import_module(contract["mechanism_module"])
    symbols = contract["data"]["symbols"]
    frames = data.load_frames(_datasets(contract), symbols, root=root)
    closes = pd.DataFrame({s: frames[module.PRICE_DATASET][s]["close"] for s in symbols})
    notional = float(contract["notional_usdt"])
    costs = contract["cost_scenarios_bps_per_fill"]
    candidates: dict[str, dict] = {}
    for key, candidate in contract["candidates"].items():
        if key not in eligible:
            candidates[key] = {"skipped": "did not pass development"}
            continue
        start, end = (candidate.get("windows") or contract["windows"])[stage]
        data.periods("daily", start, end)  # refuses the sealed blind
        weights = module.target_weights(frames, key, candidate["params"])
        result = replay.run(
            weights, closes, start=start, end=end, notional=notional, costs_bps=costs
        )
        repeat = replay.run(
            weights, closes, start=start, end=end, notional=notional, costs_bps=costs
        )
        days, held, returns = replay.window_arrays(weights, closes, start, end)
        null = gates.shift_null(
            held,
            returns,
            days,
            observed_base=result["base_net_pnl"],
            notional=notional,
            cost=costs["base"] / 1e4,
            trials=int(contract["null"]["trials"]),
            seed=int(contract["null"]["seed"]),
        )
        verdict = gates.apply_gates(contract["gates"], result, null)
        identical = repeat["daily_base_pnl_sha256"] == result["daily_base_pnl_sha256"]
        verdict["checks"]["duplicate_replay_identical"] = identical
        verdict["pass"] = verdict["pass"] and identical
        candidates[key] = {
            "source": candidate["source"],
            "model_version": candidate["model_version"],
            "window": [start, end],
            "metrics": result,
            "null": null,
            "gates": verdict,
        }

    report = {
        "schema_version": "research.result.v1",
        "protocol": contract["protocol"],
        "stage": stage,
        "contract": str(contract_path),
        "contract_sha256": contract_sha,
        "data_manifest_sha256": _manifest_digest(root, contract),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "candidates": candidates,
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    _update_registry(registry_path, contract["protocol"], stage, candidates)
    return report


def _update_registry(path: Path, protocol: int, stage: str, candidates: dict[str, dict]) -> None:
    registry = json.loads(path.read_text())
    entry = next(p for p in registry["protocols"] if p["protocol"] == protocol)
    for row in entry["candidates"]:
        result = candidates.get(row["key"], {})
        if "gates" not in result:
            continue
        if row["outcome"] == "not_opened":
            registry["totals"]["unique_identities_pnl_opened"] += 1
        if stage == "confirmation":
            registry["totals"]["confirmation_opened"] += 1
        row["outcome"] = f"{stage}_{'passed' if result['gates']['pass'] else 'rejected'}"
    registry["as_of"] = datetime.now(UTC).date().isoformat()
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")


def _summary(report: dict) -> str:
    lines = [f"v{report['protocol']} {report['stage']}"]
    for key, item in report["candidates"].items():
        if "gates" not in item:
            lines.append(f"  {key}: skipped ({item['skipped']})")
            continue
        m, g = item["metrics"], item["gates"]
        failed = [name for name, ok in g["checks"].items() if not ok]
        lines.append(
            f"  {key}: {'PASS' if g['pass'] else 'FAIL'} base={m['base_net_pnl']:.2f} "
            f"stress={m['stress_net_pnl']:.2f} bench={m['benchmark_pnl']:.2f} "
            f"p={item['null']['p_value']:.3f} positions={m['closed_positions']} "
            f"maxdd={m['max_drawdown_pct']:.1f}% failed={failed or '-'}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="download and verify the contract's data")
    fetch.add_argument("contract", type=Path)
    run = sub.add_parser("run", help="run one stage and write immutable results")
    run.add_argument("contract", type=Path)
    run.add_argument("--stage", choices=STAGES, required=True)
    args = parser.parse_args(argv)
    if args.command == "fetch":
        contract, _ = load_contract(args.contract)
        print(json.dumps(fetch_contract(contract), indent=1))
    else:
        print(_summary(run_stage(args.contract, args.stage)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
