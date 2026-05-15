from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.bridge.time_utils import ensure_ns

SCHEMA_VERSION = "signal.v1"

Side = Literal["buy", "sell", "flat"]


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
