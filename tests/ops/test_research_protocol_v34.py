import json

import pytest

from apps.ops.research_protocol_v34 import DEFAULT_PROTOCOL, load_and_validate, validate_protocol


def test_v34_pre_registration_contract_is_valid() -> None:
    result = load_and_validate(DEFAULT_PROTOCOL)
    assert result["valid"] is True
    assert result["candidate_count"] == 3
    assert result["protocol_sha256"].startswith("sha256:")
    assert result["provider_contract_sha256"].startswith("sha256:")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("data_contract", "publication_lag_calendar_days"), 0),
        (("candidates", 0, "parameters", "change_observations"), 10),
        (("parameter_lock", "parameter_tuning_forbidden"), False),
        (("boundaries", "loads_credentials"), True),
        (("execution_contract", "account_type"), "margin"),
    ],
)
def test_v34_pre_registration_rejects_drift(path: tuple, value: object) -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_protocol(payload)
