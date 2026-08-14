from __future__ import annotations

from apps.ops.research_v45_confirmation import (
    DEFAULT_CONFIRMATION_PATH,
    load_and_validate_confirmation,
)


def test_confirmation_v45_protocol_is_valid() -> None:
    result = load_and_validate_confirmation(DEFAULT_CONFIRMATION_PATH)
    assert result["valid"] is True
    assert result["protocol_sha256"].startswith("sha256:")
