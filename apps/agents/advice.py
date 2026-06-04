from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.bridge.time_utils import ensure_ns

SCHEMA_VERSION = "agent.advice.v1"

AdviceStatus = Literal["recorded", "reviewed", "archived"]
ReviewDecision = Literal["accepted", "ignored", "rejected"]

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "client_order_id",
        "leverage",
        "order_size",
        "order_type",
        "qty",
        "quantity",
        "reduce_only",
        "stop_loss",
        "submit_order",
        "take_profit",
        "time_in_force",
    }
)


class AgentAdvice(BaseModel):
    """Audited LLM/agent output that is intentionally not a SignalEvent.

    AgentAdvice is research context only. It can be reviewed by a person or a
    later offline process, but it is not part of the live order path.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal["agent.advice.v1"] = SCHEMA_VERSION
    advice_id: Annotated[str, Field(min_length=1)]
    agent_name: Annotated[str, Field(min_length=1)]
    created_at_ns: int
    advice_type: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    payload: dict[str, Any] = Field(default_factory=dict)
    tags: tuple[str, ...] = Field(default_factory=tuple)
    source_refs: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("created_at_ns")
    @classmethod
    def _created_at_in_ns(cls, value: int) -> int:
        return ensure_ns(value)

    @field_validator("agent_name", "advice_type")
    @classmethod
    def _lowercase_identifier(cls, value: str) -> str:
        if not _IDENT_RE.fullmatch(value):
            raise ValueError("must be a lowercase identifier matching [a-z][a-z0-9_]*")
        return value

    @field_validator("tags")
    @classmethod
    def _tags_are_lowercase_identifiers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not _IDENT_RE.fullmatch(value):
                raise ValueError(f"tag={value!r} must match [a-z][a-z0-9_]*")
        return values

    @model_validator(mode="after")
    def _payload_has_no_execution_directives(self) -> AgentAdvice:
        forbidden = _find_forbidden_payload_keys(self.payload)
        if forbidden:
            joined = ", ".join(sorted(forbidden))
            raise ValueError(
                "AgentAdvice payload must not contain direct execution fields: "
                f"{joined}"
            )
        return self


class AgentAdviceReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    advice_id: Annotated[str, Field(min_length=1)]
    decision: ReviewDecision
    reviewed_by: Annotated[str, Field(min_length=1)]
    reviewed_at_ns: int
    note: str | None = None

    @field_validator("reviewed_at_ns")
    @classmethod
    def _reviewed_at_in_ns(cls, value: int) -> int:
        return ensure_ns(value)


def _find_forbidden_payload_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_PAYLOAD_KEYS:
                found.add(key)
            found.update(_find_forbidden_payload_keys(nested))
    elif isinstance(value, list | tuple):
        for item in value:
            found.update(_find_forbidden_payload_keys(item))
    return found
