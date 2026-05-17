"""ADR-008 Phase 3b testnet startup guard.

This module intentionally stops at startup validation. It verifies the
credential boundary and promotion prerequisites before any future testnet
runtime is allowed to connect to an exchange adapter.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

MODE_TESTNET = "testnet"
KIND_TESTNET = "testnet"
ORDER_MODE_TESTNET = "exchange_testnet"
DATA_MODE_EXCHANGE_WS = "exchange_ws"
KEY_ENV = "BINANCE_TESTNET_API_KEY"
SECRET_ENV = "BINANCE_TESTNET_API_SECRET"
MIN_CREDENTIAL_LENGTH = 32
TESTNET_MAX_MULTIPLIER = 0.2


class StartupValidationError(ValueError):
    """Raised when ADR-008 §4.2 startup checks fail."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class GitState:
    commit: str
    dirty: bool


@dataclass(frozen=True)
class CredentialAudit:
    credentials_source: str
    credentials_key_prefix: str


@dataclass(frozen=True)
class StageEvidence:
    path: str
    decision: str
    current_stage: str | None
    target_stage: str | None


@dataclass(frozen=True)
class StartupSettings:
    mode: str
    kind: str
    allow_real_credentials: bool
    source: str
    model_version: str
    policy_position_pct_multiplier: float
    retros_dir: Path
    repo_root: Path
    operator: str = "nishiki"


@dataclass(frozen=True)
class StartupCheckResult:
    mode: str
    kind: str
    runtime_mode: str
    runtime_data_mode: str
    runtime_order_mode: str
    source: str
    model_version: str
    policy_position_pct_multiplier: float
    git_commit: str
    git_dirty: bool
    credentials_source: str
    credentials_key_prefix: str
    stage_evidence_path: str
    operator: str
    exchange_connected: bool = False
    bundle_written: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_startup(
    config: StartupSettings,
    *,
    env: Mapping[str, str] | None = None,
    git_state: GitState | None = None,
) -> StartupCheckResult:
    """Validate ADR-008 §4 startup requirements without connecting anywhere."""

    _check_mode_kind(config.mode, config.kind)
    credential_audit = _credential_audit(env or os.environ)
    if not config.allow_real_credentials:
        raise StartupValidationError(
            "allow_real_credentials_required",
            "--allow-real-credentials is required for testnet startup",
        )

    state = git_state or _git_state(config.repo_root)
    if state.dirty:
        raise StartupValidationError(
            "git_dirty",
            "testnet startup requires a clean git worktree",
        )

    if not config.source:
        raise StartupValidationError("source_required", "--source is required")
    if not config.model_version:
        raise StartupValidationError(
            "model_version_required",
            "--model-version is required",
        )
    if not 0.0 <= config.policy_position_pct_multiplier <= TESTNET_MAX_MULTIPLIER:
        raise StartupValidationError(
            "policy_multiplier_above_testnet_cap",
            "SourcePolicy.position_pct_multiplier must be in "
            f"[0, {TESTNET_MAX_MULTIPLIER}] for testnet_canary, got "
            f"{config.policy_position_pct_multiplier}",
        )

    evidence = _find_stage_evidence(
        retros_dir=config.retros_dir,
        source=config.source,
        model_version=config.model_version,
    )
    if evidence is None:
        raise StartupValidationError(
            "missing_paper_simulated_retro",
            "no decision_allowed paper_simulated hold or testnet_canary promote "
            f"retro found for {config.source} / {config.model_version}",
        )

    return StartupCheckResult(
        mode=config.mode,
        kind=config.kind,
        runtime_mode=MODE_TESTNET,
        runtime_data_mode=DATA_MODE_EXCHANGE_WS,
        runtime_order_mode=ORDER_MODE_TESTNET,
        source=config.source,
        model_version=config.model_version,
        policy_position_pct_multiplier=config.policy_position_pct_multiplier,
        git_commit=state.commit,
        git_dirty=state.dirty,
        credentials_source=f"env:{KEY_ENV},{SECRET_ENV}",
        credentials_key_prefix=credential_audit.credentials_key_prefix,
        stage_evidence_path=evidence.path,
        operator=config.operator,
    )


def _check_mode_kind(mode: str, kind: str) -> None:
    if mode != MODE_TESTNET or kind != KIND_TESTNET:
        raise StartupValidationError(
            "mode_kind_mismatch",
            "--mode testnet and --kind testnet must both be explicit",
        )


def _credential_audit(env: Mapping[str, str]) -> CredentialAudit:
    api_key = env.get(KEY_ENV, "")
    secret = env.get(SECRET_ENV, "")
    if not api_key or not secret:
        raise StartupValidationError(
            "missing_credentials",
            f"{KEY_ENV} and {SECRET_ENV} must both be set",
        )
    if len(api_key) < MIN_CREDENTIAL_LENGTH:
        raise StartupValidationError(
            "api_key_too_short",
            f"{KEY_ENV} must be at least {MIN_CREDENTIAL_LENGTH} characters",
        )
    if len(secret) < MIN_CREDENTIAL_LENGTH:
        raise StartupValidationError(
            "api_secret_too_short",
            f"{SECRET_ENV} must be at least {MIN_CREDENTIAL_LENGTH} characters",
        )
    return CredentialAudit(
        credentials_source=f"env:{KEY_ENV},{SECRET_ENV}",
        credentials_key_prefix=api_key[:8],
    )


def _git_state(repo_root: Path) -> GitState:
    root = repo_root.resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
    )
    return GitState(commit=commit, dirty=bool(status.strip()))


def _find_stage_evidence(
    *,
    retros_dir: Path,
    source: str,
    model_version: str,
) -> StageEvidence | None:
    if not retros_dir.exists():
        return None
    for path in sorted(retros_dir.glob("*.md"), reverse=True):
        evidence = _parse_retro(path)
        if evidence is None:
            continue
        if evidence["source"] != source or evidence["model_version"] != model_version:
            continue
        if not evidence["decision_allowed"]:
            continue
        decision = str(evidence["decision"]).upper()
        current_stage = evidence["current_stage"]
        target_stage = evidence["target_stage"]
        if (
            decision == "HOLD"
            and current_stage == "paper_simulated"
            and target_stage == "paper_simulated"
        ) or (decision == "PROMOTE" and target_stage == "testnet_canary"):
            return StageEvidence(
                path=str(path),
                decision=decision,
                current_stage=current_stage,
                target_stage=target_stage,
            )
    return None


def _parse_retro(path: Path) -> dict[str, object] | None:
    text = path.read_text(encoding="utf-8")
    source = _match_backticked(text, r"^- source:\s+`([^`]+)`")
    model_version = _match_backticked(text, r"^- model_version:\s+`([^`]+)`")
    if source is None or model_version is None:
        return None
    return {
        "source": source,
        "model_version": model_version,
        "current_stage": _match_backticked(text, r"^- current_stage:\s+`([^`]+)`"),
        "target_stage": _match_backticked(text, r"^- target_stage:\s+`([^`]+)`"),
        "decision": _match_bold(text, r"^- decision:\s+\*\*([^*]+)\*\*")
        or _match_bold(text, r"^- \*\*Decision\*\*:\s+(.+)$"),
        "decision_allowed": _decision_allowed(text),
    }


def _match_backticked(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _match_bold(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _decision_allowed(text: str) -> bool:
    return bool(
        re.search(r"^- decision_allowed:\s+\*\*yes\*\*", text, flags=re.MULTILINE)
        or re.search(
            r"^- \*\*Decision allowed by gates\*\*:\s+yes",
            text,
            flags=re.MULTILINE,
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate ADR-008 Phase 3b testnet startup prerequisites.",
    )
    parser.add_argument("--mode", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--allow-real-credentials", action="store_true")
    parser.add_argument("--source", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--policy-position-pct-multiplier", required=True, type=float)
    parser.add_argument("--retros-dir", type=Path, default=Path("docs/retros"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--operator", default="nishiki")
    return parser


def _config_from_args(args: argparse.Namespace) -> StartupSettings:
    return StartupSettings(
        mode=args.mode,
        kind=args.kind,
        allow_real_credentials=bool(args.allow_real_credentials),
        source=args.source,
        model_version=args.model_version,
        policy_position_pct_multiplier=args.policy_position_pct_multiplier,
        retros_dir=args.retros_dir,
        repo_root=args.repo_root,
        operator=args.operator,
    )


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    git_state: GitState | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = validate_startup(
            _config_from_args(args),
            env=env,
            git_state=git_state,
        )
    except StartupValidationError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


__all__ = [
    "CredentialAudit",
    "GitState",
    "StartupCheckResult",
    "StartupValidationError",
    "StartupSettings",
    "validate_startup",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
