from __future__ import annotations

import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from apps.agents.advice import AgentAdvice
from apps.agents.cli import main
from apps.agents.role_profiles import (
    AgentRoleProfile,
    get_agent_role_profile,
    list_agent_role_profiles,
)
from apps.bridge.signal_event import SignalEvent

REFERENCE_TS_NS = 1_778_760_000_000_000_000


def test_default_role_profiles_are_agent_advice_only() -> None:
    profiles = list_agent_role_profiles()

    assert {profile.profile_id for profile in profiles} == {
        "data_anomaly",
        "evidence_review",
        "macro_context",
        "parameter_review",
        "strategy_brainstorm",
    }
    for profile in profiles:
        assert profile.schema_version == "agent.role_profile.v1"
        assert profile.agent_name.endswith("_agent")
        assert "write_signal_event" in profile.disallowed_actions
        assert "call_exchange_api" in profile.disallowed_actions
        assert "enter_order_path" in profile.disallowed_actions

        advice = AgentAdvice(
            schema_version="agent.advice.v1",
            advice_id=f"{profile.agent_name}:{profile.advice_types[0]}:{REFERENCE_TS_NS}:abc",
            agent_name=profile.agent_name,
            created_at_ns=REFERENCE_TS_NS,
            advice_type=profile.advice_types[0],
            summary=f"{profile.display_name} configuration smoke",
            confidence=1.0,
            payload=profile.to_advice_payload(),
            tags=profile.tags,
            source_refs=("docs/progress/tradingagents-reference-map.md",),
        )
        with pytest.raises(PydanticValidationError):
            SignalEvent.model_validate(advice.model_dump())


@pytest.mark.parametrize(
    ("profile_id", "agent_name", "advice_types"),
    [
        ("trader", "trader_agent", ("strategy_note",)),
        ("portfolio", "portfolio_manager_agent", ("strategy_note",)),
        ("safe_name", "safe_agent", ("trade_decision",)),
        ("safe_name", "safe_agent", ("order_review",)),
    ],
)
def test_role_profiles_reject_execution_semantics(
    profile_id: str,
    agent_name: str,
    advice_types: tuple[str, ...],
) -> None:
    with pytest.raises(PydanticValidationError):
        AgentRoleProfile(
            profile_id=profile_id,
            agent_name=agent_name,
            display_name="Unsafe Agent",
            purpose="Should be rejected.",
            advice_types=advice_types,
            tags=("phase4",),
        )


def test_role_profile_requires_boundary_disallows() -> None:
    with pytest.raises(PydanticValidationError):
        AgentRoleProfile(
            profile_id="safe_name",
            agent_name="safe_agent",
            display_name="Safe Agent",
            purpose="Missing a required boundary.",
            advice_types=("strategy_note",),
            tags=("phase4",),
            disallowed_actions=(
                "write_signal_event",
                "mutate_source_policy",
                "call_exchange_api",
                "enter_order_path",
            ),
        )


def test_get_role_profile_by_id() -> None:
    profile = get_agent_role_profile("strategy_brainstorm")

    assert profile.agent_name == "strategy_brainstorm_agent"
    assert profile.max_debate_rounds == 1


def test_cli_profiles_outputs_safe_profiles(capsys) -> None:
    rc = main(["profiles", "--profile-id", "evidence_review"])

    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["profile_id"] for row in rows] == ["evidence_review"]
    assert rows[0]["agent_name"] == "evidence_review_agent"
    assert rows[0]["schema_version"] == "agent.role_profile.v1"
    assert "write_signal_event" in rows[0]["disallowed_actions"]
