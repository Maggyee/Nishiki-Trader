from __future__ import annotations

import time
from dataclasses import dataclass

from apps.bridge.signal_event import SCHEMA_VERSION, SignalEvent


class ValidationError(Exception):
    code: str = "invalid"


class SchemaVersionError(ValidationError):
    code = "schema_version"


class ExpiredError(ValidationError):
    code = "expired"


class UnauthorizedSourceError(ValidationError):
    code = "unauthorized_source"


class UnauthorizedModelError(ValidationError):
    code = "unauthorized_model"


@dataclass(frozen=True)
class Authorization:
    allowed_sources: frozenset[str]
    allowed_model_versions: frozenset[str]


def is_expired(event: SignalEvent, *, now_ns: int | None = None) -> bool:
    current_ns = time.time_ns() if now_ns is None else now_ns
    deadline_ns = event.ts_event + event.ttl_seconds * 1_000_000_000
    return current_ns > deadline_ns


def check_schema(event: SignalEvent) -> None:
    if event.schema_version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"schema_version={event.schema_version!r} != {SCHEMA_VERSION!r}"
        )


def check_authorization(event: SignalEvent, auth: Authorization) -> None:
    if event.source not in auth.allowed_sources:
        raise UnauthorizedSourceError(f"source={event.source!r} not in allowed list")
    if event.model_version not in auth.allowed_model_versions:
        raise UnauthorizedModelError(
            f"model_version={event.model_version!r} not in allowed list"
        )


def check_freshness(event: SignalEvent, *, now_ns: int | None = None) -> None:
    if is_expired(event, now_ns=now_ns):
        raise ExpiredError(
            f"signal_id={event.signal_id} expired "
            f"(ts_event={event.ts_event}, ttl_seconds={event.ttl_seconds})"
        )


def validate(
    event: SignalEvent,
    auth: Authorization,
    *,
    now_ns: int | None = None,
) -> None:
    check_schema(event)
    check_authorization(event, auth)
    check_freshness(event, now_ns=now_ns)
