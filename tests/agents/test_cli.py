from __future__ import annotations

import json
from pathlib import Path

from apps.agents.cli import main

REFERENCE_TS_NS = 1_778_760_000_000_000_000


def _write_jsonl(path: Path, payloads: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(p) for p in payloads), encoding="utf-8")


def _payload(advice_id: str = "a1") -> dict[str, object]:
    return {
        "schema_version": "agent.advice.v1",
        "advice_id": advice_id,
        "agent_name": "review_agent",
        "created_at_ns": REFERENCE_TS_NS,
        "advice_type": "journal",
        "summary": "testnet evidence is operational",
        "confidence": 0.8,
        "payload": {"content": "review note"},
        "tags": ["testnet"],
        "source_refs": [],
    }


def test_cli_write_then_list(tmp_path: Path, capsys) -> None:
    inp = tmp_path / "advice.jsonl"
    _write_jsonl(inp, [_payload()])
    db = tmp_path / "advice.db"

    rc = main(["--db", str(db), "write", str(inp)])
    assert rc == 0

    capsys.readouterr()
    rc = main(["--db", str(db), "list", "--agent-name", "review_agent"])
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0])["advice_id"] == "a1"


def test_cli_journal_generates_agent_advice(tmp_path: Path, capsys) -> None:
    db = tmp_path / "advice.db"

    rc = main(
        [
            "--db",
            str(db),
            "journal",
            "--agent-name",
            "review_agent",
            "--content",
            "BTCUSDT canary evidence is operational, not alpha.",
            "--tag",
            "testnet",
            "--created-at-ns",
            str(REFERENCE_TS_NS),
        ]
    )
    assert rc == 0
    written = json.loads(capsys.readouterr().out)
    assert written["schema_version"] == "agent.advice.v1"
    assert written["advice_type"] == "journal"

    main(["--db", str(db), "list", "--advice-type", "journal"])
    listed = json.loads(capsys.readouterr().out)
    assert listed["advice_id"] == written["advice_id"]


def test_cli_review(tmp_path: Path, capsys) -> None:
    inp = tmp_path / "advice.jsonl"
    _write_jsonl(inp, [_payload()])
    db = tmp_path / "advice.db"
    main(["--db", str(db), "write", str(inp)])
    capsys.readouterr()

    rc = main(
        [
            "--db",
            str(db),
            "review",
            "a1",
            "--decision",
            "ignored",
            "--reviewed-by",
            "nishiki",
            "--reviewed-at-ns",
            str(REFERENCE_TS_NS + 1),
        ]
    )

    assert rc == 0
    review = json.loads(capsys.readouterr().out)
    assert review["decision"] == "ignored"
