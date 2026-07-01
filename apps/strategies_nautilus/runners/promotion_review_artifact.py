"""Read-only parsing for promotion_review artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

EXPECTED_LIVE_CURRENT_STAGE = "testnet_canary"
EXPECTED_LIVE_TARGET_STAGE = "live_canary"
EXPECTED_LIVE_DECISION = "promote"


def evaluate_live_canary_promotion_review(
    path: Path,
    *,
    source: str,
    model_version: str,
) -> dict[str, Any]:
    """Validate a promotion_review artifact for testnet_canary -> live_canary."""

    text = path.read_text(encoding="utf-8")
    fields, parse_error = _promotion_fields(text)
    problems: list[str] = []
    if parse_error:
        problems.append(parse_error)
    if fields.get("source") != source:
        problems.append("source")
    if fields.get("model_version") != model_version:
        problems.append("model_version")
    if fields.get("current_stage") != EXPECTED_LIVE_CURRENT_STAGE:
        problems.append("current_stage")
    if fields.get("target_stage") != EXPECTED_LIVE_TARGET_STAGE:
        problems.append("target_stage")
    if _normalized(fields.get("decision")) != EXPECTED_LIVE_DECISION:
        problems.append("decision")
    if _as_bool(fields.get("decision_allowed")) is not True:
        problems.append("decision_allowed")
    if not fields.get("operator"):
        problems.append("operator")
    if _blockers(fields.get("review_blockers")):
        problems.append("review_blockers")
    if _blockers(fields.get("promotion_gate_blockers")):
        problems.append("promotion_gate_blockers")

    accepted = not problems
    return {
        "path": str(path),
        "accepted": accepted,
        "blocker": "" if accepted else "live_promotion_review_invalid",
        "detail": (
            f"{path} contains an exact signed testnet_canary -> live_canary promotion review."
            if accepted
            else "Promotion review failed exact checks: " + ", ".join(problems)
        ),
        "problems": problems,
        "fields": fields,
    }


def _promotion_fields(text: str) -> tuple[dict[str, Any], str | None]:
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return {}, f"invalid_json:{exc.msg}"
        return _json_fields(payload), None
    return _markdown_fields(text), None


def _json_fields(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {
        "source": payload.get("source"),
        "model_version": payload.get("model_version"),
        "current_stage": payload.get("current_stage"),
        "target_stage": payload.get("target_stage"),
        "decision": payload.get("decision"),
        "decision_allowed": payload.get("decision_allowed"),
        "operator": payload.get("operator"),
        "review_blockers": payload.get("review_blockers"),
        "promotion_gate_blockers": payload.get("promotion_gate_blockers"),
    }


def _markdown_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if ":" not in line:
            continue
        raw_key, raw_value = line.split(":", 1)
        key = _markdown_key(raw_key)
        value = _markdown_value(raw_value)
        if key == "decision_allowed_by_gates":
            key = "decision_allowed"
        if key in {
            "source",
            "model_version",
            "current_stage",
            "target_stage",
            "decision",
            "decision_allowed",
            "operator",
            "review_blockers",
            "promotion_gate_blockers",
        }:
            fields[key] = value
    return fields


def _markdown_key(value: str) -> str:
    value = value.replace("*", "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _markdown_value(value: str) -> str:
    value = value.strip()
    while len(value) >= 2 and (
        (value.startswith("`") and value.endswith("`"))
        or (value.startswith("**") and value.endswith("**"))
    ):
        value = value[2:-2].strip() if value.startswith("**") else value[1:-1].strip()
    return value


def _normalized(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = _normalized(value)
    if normalized in {"yes", "true", "1"}:
        return True
    if normalized in {"no", "false", "0"}:
        return False
    return None


def _blockers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    normalized = _normalized(value)
    if normalized in {"", "none", "[]"}:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


__all__ = [
    "EXPECTED_LIVE_CURRENT_STAGE",
    "EXPECTED_LIVE_DECISION",
    "EXPECTED_LIVE_TARGET_STAGE",
    "evaluate_live_canary_promotion_review",
]
