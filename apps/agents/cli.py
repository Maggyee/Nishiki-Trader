from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from apps.agents.advice import AgentAdvice
from apps.agents.store import (
    DEFAULT_ADVICE_DB_PATH,
    AgentAdviceStore,
    DuplicateAdviceError,
)


def _read_advice(path: Path) -> list[AgentAdvice]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        items = json.loads(text)
        return [AgentAdvice.model_validate(item) for item in items]

    rows: list[AgentAdvice] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(AgentAdvice.model_validate_json(line))
        except Exception as exc:
            raise SystemExit(f"{path}:{line_no}: invalid AgentAdvice: {exc}") from exc
    return rows


def _cmd_write(args: argparse.Namespace) -> int:
    store = AgentAdviceStore(args.db)
    advice_rows = _read_advice(Path(args.input))
    accepted = 0
    duplicates = 0
    for advice in advice_rows:
        try:
            store.write(advice)
            accepted += 1
        except DuplicateAdviceError:
            duplicates += 1
    print(f"wrote {accepted} accepted, {duplicates} duplicates (skipped)")
    return 0


def _cmd_journal(args: argparse.Namespace) -> int:
    created_at_ns = time.time_ns() if args.created_at_ns is None else args.created_at_ns
    payload = {"content": args.content}
    advice = AgentAdvice(
        schema_version="agent.advice.v1",
        advice_id=args.advice_id
        or _make_advice_id(
            agent_name=args.agent_name,
            advice_type="journal",
            created_at_ns=created_at_ns,
            payload=payload,
        ),
        agent_name=args.agent_name,
        created_at_ns=created_at_ns,
        advice_type="journal",
        summary=args.summary or _summarize_content(args.content),
        confidence=args.confidence,
        payload=payload,
        tags=tuple(args.tag or ()),
        source_refs=tuple(args.source_ref or ()),
    )
    store = AgentAdviceStore(args.db)
    try:
        store.write(advice)
    except DuplicateAdviceError:
        print(f"duplicate advice_id skipped: {advice.advice_id}")
        return 0
    print(advice.model_dump_json())
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    store = AgentAdviceStore(args.db)
    for advice in store.replay(
        agent_name=args.agent_name,
        advice_type=args.advice_type,
        status=args.status,
        since_ns=args.since_ns,
        until_ns=args.until_ns,
        limit=args.limit,
    ):
        sys.stdout.write(advice.model_dump_json() + "\n")
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    store = AgentAdviceStore(args.db)
    review = store.review(
        args.advice_id,
        args.decision,
        reviewed_by=args.reviewed_by,
        note=args.note,
        now_ns=args.reviewed_at_ns,
    )
    print(review.model_dump_json())
    return 0


def _make_advice_id(
    *,
    agent_name: str,
    advice_type: str,
    created_at_ns: int,
    payload: dict[str, object],
) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"{agent_name}:{advice_type}:{created_at_ns}:{digest}"


def _summarize_content(content: str) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= 160:
        return normalized
    return normalized[:157] + "..."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-advice",
        description="AgentAdvice v1 audit-store CLI",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_ADVICE_DB_PATH),
        help=f"SQLite DB path (default: {DEFAULT_ADVICE_DB_PATH})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write", help="Write AgentAdvice rows from JSON/JSONL")
    write.add_argument("input", help="Path to JSON array or JSONL file")
    write.set_defaults(func=_cmd_write)

    journal = sub.add_parser("journal", help="Write a journal AgentAdvice row")
    journal.add_argument("--agent-name", required=True)
    journal.add_argument("--content", required=True)
    journal.add_argument("--summary", default=None)
    journal.add_argument("--confidence", type=float, default=1.0)
    journal.add_argument("--tag", action="append", default=[])
    journal.add_argument("--source-ref", action="append", default=[])
    journal.add_argument("--advice-id", default=None)
    journal.add_argument("--created-at-ns", type=int, default=None)
    journal.set_defaults(func=_cmd_journal)

    list_p = sub.add_parser("list", help="Replay AgentAdvice rows as JSONL")
    list_p.add_argument("--agent-name", default=None)
    list_p.add_argument("--advice-type", default=None)
    list_p.add_argument("--status", choices=["recorded", "reviewed", "archived"], default=None)
    list_p.add_argument("--since-ns", type=int, default=None)
    list_p.add_argument("--until-ns", type=int, default=None)
    list_p.add_argument("--limit", type=int, default=100)
    list_p.set_defaults(func=_cmd_list)

    review = sub.add_parser("review", help="Attach a human review decision")
    review.add_argument("advice_id")
    review.add_argument("--decision", choices=["accepted", "ignored", "rejected"], required=True)
    review.add_argument("--reviewed-by", required=True)
    review.add_argument("--note", default=None)
    review.add_argument("--reviewed-at-ns", type=int, default=None)
    review.set_defaults(func=_cmd_review)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
