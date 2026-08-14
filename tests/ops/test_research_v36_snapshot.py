from __future__ import annotations

import pytest

from apps.ops.research_v36_snapshot import parse_and_audit_csv


def test_parse_and_audit_vpn_valid_csv() -> None:
    csv_text = b"DATE,VPN\n01/02/2020,300.5\n01/03/2020,302.1\n01/06/2020,305.0\n"
    rows, audit = parse_and_audit_csv("vpn", csv_text)
    assert len(rows) == 3
    assert audit["row_count"] == 3
    assert audit["first_date"] == "2020-01-02"
    assert audit["last_date"] == "2020-01-06"
    assert rows[0]["value"] == 300.5


def test_parse_and_audit_put_valid_csv() -> None:
    csv_text = b"DATE,PUT\n01/02/2020,1000.0\n01/03/2020,1005.5\n"
    rows, audit = parse_and_audit_csv("put", csv_text)
    assert len(rows) == 2
    assert audit["row_count"] == 2


def test_parse_and_audit_rejects_header_mismatch() -> None:
    csv_text = b"DATE,CLOSE\n01/02/2020,100.0\n"
    with pytest.raises(ValueError, match="unexpected header"):
        parse_and_audit_csv("vpn", csv_text)
