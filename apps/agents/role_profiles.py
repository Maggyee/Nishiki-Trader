from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "agent.role_profile.v1"

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_NAME_PARTS = ("trader", "portfolio", "execution")
_FORBIDDEN_ADVICE_PARTS = ("signal", "order", "trade", "execution")
_REQUIRED_DISALLOWED_ACTIONS = frozenset(
    {
        "write_signal_event",
        "mutate_source_policy",
        "call_exchange_api",
        "enter_order_path",
        "emit_execution_fields",
    }
)


class AgentRoleProfile(BaseModel):
    """Safe, non-executing role profile for future AgentAdvice producers."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal["agent.role_profile.v1"] = SCHEMA_VERSION
    profile_id: Annotated[str, Field(min_length=1)]
    agent_name: Annotated[str, Field(min_length=1)]
    display_name: Annotated[str, Field(min_length=1)]
    purpose: Annotated[str, Field(min_length=1)]
    input_refs: tuple[str, ...] = Field(default_factory=tuple)
    advice_types: tuple[str, ...] = Field(default_factory=tuple)
    tags: tuple[str, ...] = Field(default_factory=tuple)
    tradingagents_patterns: tuple[str, ...] = Field(default_factory=tuple)
    max_debate_rounds: Annotated[int, Field(ge=0, le=1)] = 0
    disallowed_actions: tuple[str, ...] = Field(
        default=tuple(sorted(_REQUIRED_DISALLOWED_ACTIONS))
    )

    @field_validator("profile_id", "agent_name")
    @classmethod
    def _safe_agent_identifier(cls, value: str) -> str:
        _validate_identifier(value)
        for part in _FORBIDDEN_NAME_PARTS:
            if part in value:
                raise ValueError(f"agent role identifiers must not contain {part!r}")
        return value

    @field_validator("advice_types", "tags")
    @classmethod
    def _tuple_identifiers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _validate_identifier(value)
        return values

    @field_validator("advice_types")
    @classmethod
    def _advice_types_are_not_execution_semantics(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not values:
            raise ValueError("at least one advice_type is required")
        for value in values:
            for part in _FORBIDDEN_ADVICE_PARTS:
                if part in value:
                    raise ValueError(f"advice_type must not contain {part!r}")
        return values

    @model_validator(mode="after")
    def _keeps_required_boundaries(self) -> AgentRoleProfile:
        missing = _REQUIRED_DISALLOWED_ACTIONS.difference(self.disallowed_actions)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"missing required disallowed actions: {joined}")
        return self

    def to_advice_payload(self) -> dict[str, object]:
        """Return a payload that can be embedded in an AgentAdvice row."""

        return {
            "role_profile_id": self.profile_id,
            "purpose": self.purpose,
            "input_refs": list(self.input_refs),
            "allowed_advice_types": list(self.advice_types),
            "tradingagents_reference_patterns": list(self.tradingagents_patterns),
            "max_debate_rounds": self.max_debate_rounds,
            "boundaries": {
                action: False
                for action in (
                    "write_signal_event",
                    "mutate_source_policy",
                    "call_exchange_api",
                    "enter_order_path",
                    "emit_execution_fields",
                )
            },
        }


def list_agent_role_profiles() -> tuple[AgentRoleProfile, ...]:
    return DEFAULT_AGENT_ROLE_PROFILES


def get_agent_role_profile(profile_id: str) -> AgentRoleProfile:
    for profile in DEFAULT_AGENT_ROLE_PROFILES:
        if profile.profile_id == profile_id:
            return profile
    raise KeyError(f"unknown agent role profile: {profile_id}")


def _validate_identifier(value: str) -> None:
    if not _IDENT_RE.fullmatch(value):
        raise ValueError("must be a lowercase identifier matching [a-z][a-z0-9_]*")


DEFAULT_AGENT_ROLE_PROFILES: tuple[AgentRoleProfile, ...] = (
    AgentRoleProfile(
        profile_id="evidence_review",
        agent_name="evidence_review_agent",
        display_name="Evidence Review Agent",
        purpose="Review current project status, canary evidence, and bundle reports.",
        input_refs=(
            "docs/project-status.md",
            "docs/progress/phase-3-testnet-canary-evidence.md",
            "docs/progress/phase-3-testnet-continuity-plan.md",
        ),
        advice_types=("evidence_review", "project_review"),
        tags=("phase4", "review", "evidence"),
        tradingagents_patterns=("research_manager", "bounded_review"),
    ),
    AgentRoleProfile(
        profile_id="data_anomaly",
        agent_name="data_anomaly_agent",
        display_name="Data Anomaly Agent",
        purpose="Summarize passive dashboard, observability, and sidecar anomalies.",
        input_refs=(
            "dashboard.snapshot.v1",
            "data/observability/textfile/*.prom",
            "data/testnet/<run_id>/",
        ),
        advice_types=("anomaly_observation",),
        tags=("phase5", "observability", "review"),
        tradingagents_patterns=("analyst_team_reports", "report_sections"),
    ),
    AgentRoleProfile(
        profile_id="macro_context",
        agent_name="macro_context_agent",
        display_name="Macro Context Agent",
        purpose="Summarize approved macro or news context once a source is reviewed.",
        input_refs=("approved local macro/news artifacts",),
        advice_types=("market_context",),
        tags=("phase4", "macro", "context"),
        tradingagents_patterns=("news_analyst", "sentiment_analyst"),
    ),
    AgentRoleProfile(
        profile_id="strategy_brainstorm",
        agent_name="strategy_brainstorm_agent",
        display_name="Strategy Brainstorm Agent",
        purpose="Generate research notes and critique ideas for human review.",
        input_refs=("historical reports", "rejected signal summaries", "user prompts"),
        advice_types=("strategy_note",),
        tags=("phase4", "research", "brainstorm"),
        tradingagents_patterns=("bull_bear_debate", "research_manager"),
        max_debate_rounds=1,
    ),
    AgentRoleProfile(
        profile_id="parameter_review",
        agent_name="parameter_review_agent",
        display_name="Parameter Review Agent",
        purpose="Review paper/testnet evidence for non-binding parameter candidates.",
        input_refs=(
            "docs/retros/",
            "docs/progress/phase-3-testnet-canary-evidence.md",
            "SourcePolicy documentation",
        ),
        advice_types=("parameter_candidate",),
        tags=("phase4", "parameters", "review"),
        tradingagents_patterns=("risk_discussion", "portfolio_review_recast"),
    ),
)

__all__ = [
    "AgentRoleProfile",
    "DEFAULT_AGENT_ROLE_PROFILES",
    "SCHEMA_VERSION",
    "get_agent_role_profile",
    "list_agent_role_profiles",
]
