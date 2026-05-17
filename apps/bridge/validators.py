from __future__ import annotations

import time
from dataclasses import dataclass, field

from apps.bridge.signal_event import SCHEMA_VERSION, SOURCE_FAMILIES, SignalEvent

WILDCARD = "*"
_FAMILY_PREFIXES = tuple(f"{f}_" for f in SOURCE_FAMILIES)


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
class SourcePolicy:
    """ADR-006 per-(source, model_version) consumer-side policy.

    `position_pct_multiplier`: scales the strategy's `target_position_pct` for
    accepted signals. 0.0 zeroes the target but still records lineage; the
    `dry_run` flag is the canonical way to keep target sizing intact while
    suppressing order submission.

    `min_confidence_override`: tighter floor on `event.confidence`. Effective
    threshold is always `max(strategy.min_confidence, override)` — the policy
    cannot loosen the strategy's default.

    `dry_run`: when True, consumers must still emit an `OrderIntent` for
    auditability but skip the actual order submission.
    """

    position_pct_multiplier: float = 1.0
    min_confidence_override: float | None = None
    dry_run: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.position_pct_multiplier <= 1.0:
            raise ValueError(
                f"position_pct_multiplier must be in [0, 1], "
                f"got {self.position_pct_multiplier}"
            )
        if self.min_confidence_override is not None and not (
            0.0 <= self.min_confidence_override <= 1.0
        ):
            raise ValueError(
                f"min_confidence_override must be in [0, 1] or None, "
                f"got {self.min_confidence_override}"
            )


_DEFAULT_POLICY = SourcePolicy()


@dataclass(frozen=True)
class Authorization:
    allowed_sources: frozenset[str]
    allowed_model_versions: frozenset[str]
    policies: dict[tuple[str, str], SourcePolicy] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key in self.policies:
            if not isinstance(key, tuple) or len(key) != 2:
                raise ValueError(
                    f"policies keys must be (source, model_version) tuples, got {key!r}"
                )
            source, model_version = key
            if not isinstance(source, str) or not isinstance(model_version, str):
                raise ValueError(
                    f"policies key {key!r} must contain two strings"
                )
            if source != WILDCARD and not source.startswith(_FAMILY_PREFIXES):
                raise ValueError(
                    f"policies source {source!r} must match ADR-005 §2.1 "
                    f"prefix or be {WILDCARD!r}"
                )

    def policy_for(self, source: str, model_version: str) -> SourcePolicy:
        """Resolve the policy for one (source, model_version).

        Precision order (ADR-006 §2.2):
            1. (source, model_version)
            2. (source, WILDCARD)
            3. (WILDCARD, model_version)
            4. (WILDCARD, WILDCARD)
            5. SourcePolicy()  # default
        Returns the first hit; never merges multiple policies.
        """
        for key in (
            (source, model_version),
            (source, WILDCARD),
            (WILDCARD, model_version),
            (WILDCARD, WILDCARD),
        ):
            if key in self.policies:
                return self.policies[key]
        return _DEFAULT_POLICY


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
