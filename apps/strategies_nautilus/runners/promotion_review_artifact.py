"""Read-only parsing for promotion_review artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

EXPECTED_LIVE_CURRENT_STAGE = "testnet_canary"
EXPECTED_LIVE_TARGET_STAGE = "live_canary"
EXPECTED_LIVE_DECISION = "promote"
EXPECTED_TESTNET_CURRENT_STAGE = "paper_simulated"
EXPECTED_TESTNET_TARGET_STAGE = "testnet_canary"
EXPECTED_TESTNET_DECISION = "promote"


def evaluate_live_canary_promotion_review(
    path: Path,
    *,
    source: Any,
    model_version: Any,
) -> dict[str, Any]:
    """Validate a promotion_review artifact for testnet_canary -> live_canary."""

    raw = path.read_bytes()
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {
            "path": str(path),
            "sha256": artifact_sha256,
            "accepted": False,
            "blocker": "live_promotion_review_invalid",
            "detail": f"Promotion review is not valid UTF-8: {exc}",
            "problems": ["invalid_utf8"],
            "fields": {},
            "decode_error": str(exc),
        }
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
        "sha256": artifact_sha256,
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


def evaluate_testnet_canary_policy_review(
    path: Path,
    *,
    source: Any,
    model_version: Any,
) -> dict[str, Any]:
    """Validate the signed policy evidence linked by a testnet manifest."""

    if not path.is_file():
        return {
            "path": str(path),
            "sha256": None,
            "accepted": False,
            "blocker": "testnet_policy_review_not_found",
            "detail": f"Promotion review does not exist: {path}",
            "problems": ["not_found"],
            "fields": {},
            "policy": None,
        }

    raw = path.read_bytes()
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {
            "path": str(path),
            "sha256": artifact_sha256,
            "accepted": False,
            "blocker": "testnet_policy_review_invalid",
            "detail": f"Promotion review is not valid UTF-8: {exc}",
            "problems": ["invalid_utf8"],
            "fields": {},
            "policy": None,
        }

    fields, parse_error = _promotion_fields(text)
    problems: list[str] = []
    if parse_error:
        problems.append(parse_error)
    if fields.get("source") != source:
        problems.append("source")
    if fields.get("model_version") != model_version:
        problems.append("model_version")
    if fields.get("current_stage") != EXPECTED_TESTNET_CURRENT_STAGE:
        problems.append("current_stage")
    if fields.get("target_stage") != EXPECTED_TESTNET_TARGET_STAGE:
        problems.append("target_stage")
    if _normalized(fields.get("decision")) != EXPECTED_TESTNET_DECISION:
        problems.append("decision")
    if _as_bool(fields.get("decision_allowed")) is not True:
        problems.append("decision_allowed")
    if not fields.get("operator"):
        problems.append("operator")
    if _blockers(fields.get("review_blockers")):
        problems.append("review_blockers")
    if _blockers(fields.get("promotion_gate_blockers")):
        problems.append("promotion_gate_blockers")

    policy, policy_problems = _source_policy(fields.get("target_policy"))
    problems.extend(policy_problems)
    if policy is not None and policy["dry_run"] is not False:
        problems.append("target_policy.dry_run_for_testnet")
    accepted = not problems
    return {
        "path": str(path),
        "sha256": artifact_sha256,
        "accepted": accepted,
        "blocker": "" if accepted else "testnet_policy_review_invalid",
        "detail": (
            f"{path} contains an exact signed paper_simulated -> testnet_canary promotion policy."
            if accepted
            else "Promotion review failed exact checks: " + ", ".join(problems)
        ),
        "problems": problems,
        "fields": fields,
        "policy": policy if accepted else None,
    }


def promotion_review_sha256(path: Path) -> str:
    """Return the SHA-256 fingerprint for the exact artifact bytes."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _promotion_fields(text: str) -> tuple[dict[str, Any], str | None]:
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(
                text,
                parse_constant=_reject_non_standard_json_constant,
            )
        except ValueError as exc:
            message = getattr(exc, "msg", str(exc))
            return {}, f"invalid_json:{message}"
        return _json_fields(payload), None
    return _markdown_fields(text), None


def _reject_non_standard_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


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
        "current_policy": payload.get("current_policy"),
        "target_policy": payload.get("target_policy"),
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
        value: Any = _markdown_value(raw_value)
        if key == "decision_allowed_by_gates":
            key = "decision_allowed"
        if key in {"current_policy", "target_policy"}:
            value = _markdown_policy(value)
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
            "current_policy",
            "target_policy",
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


def _markdown_policy(value: str) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    for item in value.split(","):
        if "=" not in item:
            continue
        raw_key, raw_value = item.split("=", 1)
        key = raw_key.strip()
        normalized = raw_value.strip()
        if normalized == "True":
            parsed: Any = True
        elif normalized == "False":
            parsed = False
        elif normalized == "None":
            parsed = None
        else:
            try:
                parsed = float(normalized)
            except ValueError:
                parsed = normalized
        policy[key] = parsed
    return policy


def _source_policy(value: Any) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(value, dict):
        return None, ["target_policy"]

    problems: list[str] = []
    dry_run = value.get("dry_run")
    if not isinstance(dry_run, bool):
        problems.append("target_policy.dry_run")

    multiplier = value.get("position_pct_multiplier")
    if (
        isinstance(multiplier, bool)
        or not isinstance(multiplier, int | float)
        or not math.isfinite(float(multiplier))
        or not 0.0 <= float(multiplier) <= 0.2
    ):
        problems.append("target_policy.position_pct_multiplier")

    override = value.get("min_confidence_override")
    if override is not None and (
        isinstance(override, bool)
        or not isinstance(override, int | float)
        or not math.isfinite(float(override))
        or not 0.0 <= float(override) <= 1.0
    ):
        problems.append("target_policy.min_confidence_override")

    if problems:
        return None, problems
    return {
        "dry_run": dry_run,
        "position_pct_multiplier": float(multiplier),
        "min_confidence_override": (None if override is None else float(override)),
    }, []


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
    "EXPECTED_TESTNET_CURRENT_STAGE",
    "EXPECTED_TESTNET_DECISION",
    "EXPECTED_TESTNET_TARGET_STAGE",
    "evaluate_live_canary_promotion_review",
    "evaluate_testnet_canary_policy_review",
    "promotion_review_sha256",
]
