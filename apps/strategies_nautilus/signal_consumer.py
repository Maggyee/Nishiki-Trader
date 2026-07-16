from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError as PydanticValidationError

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.bridge.validators import (
    Authorization,
    ExpiredError,
    SchemaVersionError,
    UnauthorizedModelError,
    UnauthorizedSourceError,
    check_authorization,
    check_freshness,
    check_schema,
)

logger = logging.getLogger(__name__)

Decision = Literal[
    "accept",
    "reject_schema",
    "reject_venue",
    "reject_unauthorized_source",
    "reject_unauthorized_model",
    "reject_low_confidence",
    "expired",
]


@dataclass(frozen=True)
class ConsumerConfig:
    venue: str
    auth: Authorization
    min_confidence: float = 0.5


@dataclass(frozen=True)
class ConsumerOutcome:
    signal_id: str
    decision: Decision
    reason: str | None = None


def evaluate(
    event: SignalEvent,
    config: ConsumerConfig,
    *,
    now_ns: int | None = None,
) -> ConsumerOutcome:
    try:
        check_schema(event)
    except SchemaVersionError as exc:
        return ConsumerOutcome(event.signal_id, "reject_schema", str(exc))

    if event.venue != config.venue:
        return ConsumerOutcome(
            event.signal_id,
            "reject_venue",
            f"venue={event.venue!r} != consumer venue={config.venue!r}",
        )

    try:
        check_authorization(event, config.auth)
    except UnauthorizedSourceError as exc:
        return ConsumerOutcome(event.signal_id, "reject_unauthorized_source", str(exc))
    except UnauthorizedModelError as exc:
        return ConsumerOutcome(event.signal_id, "reject_unauthorized_model", str(exc))

    try:
        check_freshness(event, now_ns=now_ns)
    except ExpiredError as exc:
        return ConsumerOutcome(event.signal_id, "expired", str(exc))

    if event.confidence < config.min_confidence:
        return ConsumerOutcome(
            event.signal_id,
            "reject_low_confidence",
            f"confidence={event.confidence:.3f} < min={config.min_confidence:.3f}",
        )

    return ConsumerOutcome(event.signal_id, "accept", None)


_STATUS_BY_DECISION: dict[Decision, str] = {
    "accept": "consumed",
    "expired": "expired",
    "reject_schema": "rejected",
    "reject_venue": "rejected",
    "reject_unauthorized_source": "rejected",
    "reject_unauthorized_model": "rejected",
    "reject_low_confidence": "rejected",
}


class SignalConsumer:
    """Phase 1 placeholder consumer.

    Reads pending SignalEvents from SignalStore, applies ADR-002 §4.1
    strategy-side checks, marks store rows accordingly, and emits
    ConsumerOutcomes. Does NOT call any trading API.
    """

    def __init__(self, store: SignalStore, config: ConsumerConfig) -> None:
        self.store = store
        self.config = config

    def consume_pending(self, *, now_ns: int | None = None) -> list[ConsumerOutcome]:
        outcomes: list[ConsumerOutcome] = []
        for row in self.store.list_by_status("pending"):
            try:
                event = SignalEvent.model_validate_json(row["raw_json"])
            except PydanticValidationError as exc:
                self.store.mark(row["signal_id"], "rejected", reason=f"parse_error: {exc}")
                outcomes.append(
                    ConsumerOutcome(row["signal_id"], "reject_schema", f"parse_error: {exc}")
                )
                continue

            outcome = evaluate(event, self.config, now_ns=now_ns)
            status = _STATUS_BY_DECISION[outcome.decision]
            self.store.mark(
                event.signal_id,
                status,  # type: ignore[arg-type]
                reason=outcome.reason,
                now_ns=now_ns,
            )
            logger.info(
                "signal %s -> %s (%s)",
                event.signal_id,
                outcome.decision,
                outcome.reason or "ok",
            )
            outcomes.append(outcome)
        return outcomes
