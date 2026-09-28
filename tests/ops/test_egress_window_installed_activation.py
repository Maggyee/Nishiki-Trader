"""Installed-source selection and one-shot nft activation share a disposable root."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "infra/egress-guard/gateway_window_installation_selftest.py"
)


def test_installed_sources_join_real_isolated_one_shot_activation(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("installed_joint_activation_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report_path = tmp_path / "installed-joint-window.json"
    assert module.main(["--report", str(report_path)]) == 0
    report = json.loads(report_path.read_bytes())
    status = json.loads(capsys.readouterr().out)
    assert status["report_sha256"] == module.sha(report_path.read_bytes())
    assert status["checks"] == 18
    assert report["base_checks"] == 40
    assert report["host_observations_unchanged"] is True
    assert report["host_installation_performed"] is False
    assert report["venue_requests_made"] == 0
    assert report["network_admitted"] is False
    activation = report["activation_probe"]
    assert activation["status"] == "local_blackout_transaction_observed_unqualified"
    assert activation["observations"] == 1
    for key in (
        "activation_history_verified",
        "source_authenticated",
        "complete_caller_coverage_verified",
        "network_admitted",
    ):
        assert activation[key] is False
    assert re.fullmatch("[0-9a-f]{64}", activation["selection_sha256"])
    assert re.fullmatch("[0-9a-f]{64}", activation["archive_sha256"])
