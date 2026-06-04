from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from apps.agents.advice import AgentAdvice
from apps.bridge.signal_event import SignalEvent

REFERENCE_TS_NS = 1_778_760_000_000_000_000


def _advice_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "agent.advice.v1",
        "advice_id": "review_agent:journal:1778760000000000000:abc",
        "agent_name": "review_agent",
        "created_at_ns": REFERENCE_TS_NS,
        "advice_type": "journal",
        "summary": "testnet evidence is operational, not alpha",
        "confidence": 0.8,
        "payload": {"content": "summarize the latest canary evidence"},
        "tags": ("testnet", "retro"),
        "source_refs": ("docs/progress/phase-3-testnet-canary-evidence.md",),
    }
    base.update(overrides)
    return base


def test_agent_advice_parses() -> None:
    advice = AgentAdvice.model_validate(_advice_payload())

    assert advice.schema_version == "agent.advice.v1"
    assert advice.agent_name == "review_agent"
    assert advice.advice_type == "journal"
    assert advice.tags == ("testnet", "retro")


def test_agent_advice_rejects_signal_schema() -> None:
    with pytest.raises(PydanticValidationError):
        AgentAdvice.model_validate({"schema_version": "signal.v1"})


def test_agent_advice_cannot_be_signal_event() -> None:
    advice = AgentAdvice.model_validate(_advice_payload())

    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(advice.model_dump())


@pytest.mark.parametrize(
    "field",
    [
        "advice_id",
        "agent_name",
        "created_at_ns",
        "advice_type",
        "summary",
        "confidence",
    ],
)
def test_missing_required_field_rejected(field: str) -> None:
    payload = _advice_payload()
    payload.pop(field)

    with pytest.raises(PydanticValidationError):
        AgentAdvice.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"order_type": "market"},
        {"nested": {"quantity": "0.001"}},
        {"ideas": [{"leverage": 2}]},
        {"risk": {"take_profit": "80000"}},
    ],
)
def test_payload_rejects_direct_execution_fields(payload: dict[str, object]) -> None:
    with pytest.raises(PydanticValidationError):
        AgentAdvice.model_validate(_advice_payload(payload=payload))


@pytest.mark.parametrize(
    "bad_value",
    ["ReviewAgent", "review-agent", "review agent", "_review_agent"],
)
def test_agent_name_must_be_lowercase_identifier(bad_value: str) -> None:
    with pytest.raises(PydanticValidationError):
        AgentAdvice.model_validate(_advice_payload(agent_name=bad_value))


def test_created_at_must_be_ns() -> None:
    with pytest.raises(PydanticValidationError):
        AgentAdvice.model_validate(_advice_payload(created_at_ns=1_778_760_000_000))
