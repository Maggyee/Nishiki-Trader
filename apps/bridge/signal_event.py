from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.bridge.side_semantics import side_score_conflict_reason
from apps.bridge.time_utils import ensure_ns

SCHEMA_VERSION = "signal.v1"

Side = Literal["buy", "sell", "flat"]

SOURCE_FAMILIES: tuple[str, ...] = ("manual", "rule", "freqai", "llm")
_SOURCE_RE = re.compile(
    r"^(?:" + "|".join(SOURCE_FAMILIES) + r")_[a-z0-9][a-z0-9_]*$"
)


class SignalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal["signal.v1"] = SCHEMA_VERSION
    signal_id: Annotated[str, Field(min_length=1)]
    symbol: Annotated[str, Field(min_length=1)]
    venue: Annotated[str, Field(min_length=1)]
    ts_event: int
    horizon: Annotated[str, Field(min_length=1)]
    side: Side
    score: Annotated[float, Field(ge=-1.0, le=1.0)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    source: Annotated[str, Field(min_length=1)]
    model_version: Annotated[str, Field(min_length=1)]
    ttl_seconds: Annotated[int, Field(gt=0)]
    features_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ts_event")
    @classmethod
    def _ts_event_in_ns(cls, v: int) -> int:
        return ensure_ns(v)

    @field_validator("source")
    @classmethod
    def _source_family_prefix(cls, v: str) -> str:
        if not _SOURCE_RE.fullmatch(v):
            raise ValueError(
                f"source={v!r} must match `<family>_<variant>` where family in "
                f"{SOURCE_FAMILIES} and variant is lowercase a-z0-9_ (ADR-005 §2.1)"
            )
        return v

    @model_validator(mode="after")
    def _side_score_consistent(self) -> SignalEvent:
        reason = side_score_conflict_reason(self.side, self.score)
        if reason is not None:
            raise ValueError(reason)
        return self
