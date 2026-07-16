from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from apps.bridge.cli import main


def _write_jsonl(path: Path, payloads: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(p) for p in payloads), encoding="utf-8")


def test_cli_write_then_replay(tmp_path, signal_payload, capsys):
    inp = tmp_path / "signals.jsonl"
    _write_jsonl(inp, [signal_payload])
    db = tmp_path / "signals.db"

    rc = main(["--db", str(db), "write", str(inp)])
    assert rc == 0

    capsys.readouterr()
    rc = main([
        "--db", str(db),
        "replay",
        "--now-ns", str(signal_payload["ts_event"]),
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0])["signal_id"] == signal_payload["signal_id"]


def test_cli_write_module_entrypoint(tmp_path):
    inp = tmp_path / "empty.jsonl"
    inp.write_text("", encoding="utf-8")
    db = tmp_path / "signals.db"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "apps.bridge.cli",
            "--db",
            str(db),
            "write",
            str(inp),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "wrote 0 accepted" in completed.stdout


def test_cli_write_dedupes_on_second_run(tmp_path, signal_payload, capsys):
    inp = tmp_path / "signals.jsonl"
    _write_jsonl(inp, [signal_payload])
    db = tmp_path / "signals.db"

    main(["--db", str(db), "write", str(inp)])
    capsys.readouterr()
    main(["--db", str(db), "write", str(inp)])
    out = capsys.readouterr().out
    assert "1 duplicates" in out

    conn = sqlite3.connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    finally:
        conn.close()
    assert count == 1


def test_cli_validate_rejects_unauthorized(tmp_path, make_payload, capsys):
    inp = tmp_path / "signals.jsonl"
    _write_jsonl(inp, [make_payload(source="llm_rogue", signal_id="rogue-1")])
    rc = main([
        "validate",
        "--allowed-sources", "freqai_v1",
        "--allowed-models", "2026-05-14",
        str(inp),
    ])
    assert rc == 1
    out = capsys.readouterr().out
    assert "unauthorized_source" in out


def test_cli_replay_filters_expired_by_default(tmp_path, signal_payload, capsys):
    inp = tmp_path / "signals.jsonl"
    _write_jsonl(inp, [signal_payload])
    db = tmp_path / "signals.db"
    main(["--db", str(db), "write", str(inp)])
    capsys.readouterr()

    expired_now = signal_payload["ts_event"] + (signal_payload["ttl_seconds"] + 10) * 1_000_000_000
    main(["--db", str(db), "replay", "--now-ns", str(expired_now)])
    assert capsys.readouterr().out.strip() == ""

    main(["--db", str(db), "replay", "--now-ns", str(expired_now), "--include-expired"])
    assert capsys.readouterr().out.strip() != ""


def test_cli_write_enforces_consumer_policy(tmp_path, signal_payload):
    inp = tmp_path / "signals.jsonl"
    _write_jsonl(inp, [signal_payload])
    db = tmp_path / "signals.db"

    rc = main([
        "--db", str(db),
        "write",
        "--enforce-consumer-policy",
        "--allowed-sources", "freqai_v1",
        "--allowed-models", "2026-05-14",
        "--venue", "BINANCE",
        "--now-ns", str(signal_payload["ts_event"]),
        str(inp),
    ])
    assert rc == 0
    conn = sqlite3.connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    finally:
        conn.close()
    assert count == 1


def test_cli_write_rejects_unauthorized_with_consumer_policy(tmp_path, make_payload):
    inp = tmp_path / "signals.jsonl"
    payload = make_payload(source="llm_rogue", signal_id="rogue-1")
    _write_jsonl(inp, [payload])
    db = tmp_path / "signals.db"

    rc = main([
        "--db", str(db),
        "write",
        "--enforce-consumer-policy",
        "--allowed-sources", "freqai_v1",
        "--allowed-models", "2026-05-14",
        "--now-ns", str(payload["ts_event"]),
        str(inp),
    ])
    assert rc == 1
    conn = sqlite3.connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    finally:
        conn.close()
    assert count == 0
