from __future__ import annotations

from apps.ops.research_v46_confirmation import (
    DEFAULT_CONFIRMATION_PATH,
    load_and_validate_confirmation,
)


def test_confirmation_v46_protocol_is_valid() -> None:
    result = load_and_validate_confirmation(DEFAULT_CONFIRMATION_PATH)
    assert result["valid"] is True
    assert result["protocol_sha256"].startswith("sha256:")
