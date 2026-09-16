"""Historical original receipts cannot refresh counters or authorize joint dispatch."""

import json
import socket
import subprocess
import sys

import pytest

from apps.ops.portfolio_joint_admission import main, review_bootstrap
from apps.strategies_nautilus.portfolio_joint_admission import sha
from tests.ops.test_portfolio_rest_bootstrap_review import capture as capture

S = 1_000_000_000
WALL = 3600 * S
MONO = 100 * S


def encode(rows):
    previous = None
    output = b""
    for i, source in enumerate(rows):
        row = {**source, "seq": i, "previous_sha256": previous}
        line = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        previous = sha(line)
        output += line
    return output


@pytest.fixture
def evidence(capture):
    plan_raw, rows, response = capture
    plan = json.loads(plan_raw)
    plan.update(
        source_commit="fixture",
        collector={"name": "trader-egress", "uid": 997, "gid": 997},
        private_ipv4="10.0.0.136",
        public_ipv4="198.51.100.1",
        host_boot_id="fixture-boot",
        installation_manifest_sha256="1" * 64,
        operator_mapping_sha256="2" * 64,
        maintenance_accepted=True,
        unknown_prior_usage_accepted=True,
    )
    plan_raw = json.dumps(plan).encode()
    rows[0].update(plan_sha256=sha(plan_raw), source_commit="fixture")
    rows[2]["identity"] = {
        "uids": [997] * 4,
        "gids": [997] * 4,
        "groups": [],
        "capabilities": {"CapEff": 0},
        "no_new_privileges": 1,
    }
    rows[3].update(collector_ms=12000, blackout_ms=20000)
    rows[5].update(destination=plan["destination_ipv4"], port=443)
    rows[6]["local"] = ["169.254.254.2", 12345]
    for i, row in enumerate(rows):
        elapsed = i * 10_000_000 + (8 * S if i >= 9 else 0)
        row.update(utc_ns=WALL + elapsed, monotonic_ns=MONO + elapsed)
    return plan_raw, rows, response


def call(evidence, **kwargs):
    plan, rows, response = evidence
    return review_bootstrap(
        plan,
        encode(rows),
        response,
        at_ns=kwargs.pop("at_ns", WALL + 10 * S),
        monotonic_ns=kwargs.pop("monotonic_ns", MONO + 10 * S),
        boot_id=kwargs.pop("boot_id", "fixture-boot"),
        **kwargs,
    )


def test_slow_body_cannot_refresh_header_counter(evidence):
    r = call(evidence)
    c = r["bootstrap_context"]
    assert c["header_already_stale_at_body_completion"]
    assert c["header_receipt_age_ns"] == 9_920_000_000
    assert c["header_to_complete_ns"] == 8_010_000_000
    assert "bootstrap_counter_stale_before_body_completed" in r["blockers"]
    assert "fresh_qualified_rest_dispatch_sample_missing" in r["blockers"]
    assert r["interval_reviews"][0]["count"] == 20
    assert r["interval_reviews"][0]["headroom_after_documented_reservation"] is None
    assert r["maximum_scope"]["rest_get_count"] == 17
    assert r["maximum_scope"]["total_documented_weight"] == 468
    assert r["bootstrap_scope_consumed"] and not r["joint_scope_consumed"]
    assert not any(
        r[k]
        for k in [
            "network_admitted",
            "capacity_reserved",
            "restart_allowed",
            "trading_admitted",
            "source_authenticated",
            "shared_egress_verified",
        ]
    )


def test_split_headers_use_receipt_containing_last_header_byte(evidence):
    plan, rows, response = evidence
    cut = 20
    rows[8].update(size=cut, sha256=sha(response[:cut]))
    second = {
        **rows[8],
        "size": len(response) - cut,
        "sha256": sha(response[cut:]),
        "utc_ns": WALL + S,
        "monotonic_ns": MONO + S,
    }
    rows.insert(9, second)
    r = call((plan, rows, response))
    assert r["bootstrap_context"]["header_persisted_monotonic_ns"] == MONO + S


@pytest.mark.parametrize("offset,stale", [(0, False), (1, True)])
def test_exact_five_second_receipt_age_boundary(evidence, offset, stale):
    _, rows, _ = evidence
    for row in rows[9:]:
        row["utc_ns"] -= 8 * S
        row["monotonic_ns"] -= 8 * S
    at = rows[8]["utc_ns"] + 5 * S + offset
    mono = rows[8]["monotonic_ns"] + 5 * S + offset
    r = call(evidence, at_ns=at, monotonic_ns=mono)
    assert ("bootstrap_header_receipt_stale_at_review" in r["blockers"]) is stale
    assert not r["network_admitted"]
    assert "qualified_server_clock_interval_missing" in r["blockers"]


@pytest.mark.parametrize("change", ["boot", "wall", "mono", "before_cleanup", "receipt_drift"])
def test_incomparable_clocks_do_not_supply_age(evidence, change):
    args = {}
    if change == "boot":
        args["boot_id"] = "another-boot"
    if change == "wall":
        args["at_ns"] = WALL + 11 * S
    if change == "mono":
        args["monotonic_ns"] = MONO + 11 * S
    if change == "before_cleanup":
        args.update(at_ns=WALL + S, monotonic_ns=MONO + S)
    if change == "receipt_drift":
        evidence[1][8]["utc_ns"] += S
    r = call(evidence, **args)
    assert r["bootstrap_context"]["header_receipt_age_ns"] is None
    assert "bootstrap_review_clock_or_boot_not_comparable" in r["blockers"]
    assert not r["network_admitted"]


@pytest.mark.parametrize("change", ["commit", "destination", "uid", "cap", "local", "window"])
def test_rehashed_cross_record_identity_changes_are_refused(evidence, change):
    _, rows, _ = evidence
    if change == "commit":
        rows[0]["source_commit"] = "other"
    if change == "destination":
        rows[5]["destination"] = "192.0.2.2"
    if change == "uid":
        rows[2]["identity"]["uids"][0] = 0
    if change == "cap":
        rows[2]["identity"]["capabilities"]["CapEff"] = 1
    if change == "local":
        rows[6]["local"][0] = "127.0.0.1"
    if change == "window":
        rows[3]["collector_ms"] = 20000
    with pytest.raises(ValueError):
        call(evidence)


def test_incomplete_scope_is_not_imported_as_rate_sample(evidence):
    plan, rows, response = evidence
    r = call((plan, rows[:9], response))
    assert "bootstrap_incomplete_or_failed_no_dispatch_sample" in r["blockers"]
    assert r["interval_reviews"] == []
    assert not r["restart_allowed"]


def arguments(evidence, tmp_path):
    plan, rows, response = evidence
    args = []
    for name, raw in [("plan", plan), ("events", encode(rows)), ("response", response)]:
        p = tmp_path / name
        p.write_bytes(raw)
        p.chmod(0o600)
        args += ["--bootstrap-" + name, str(p), "--bootstrap-" + name + "-sha256", sha(raw)]
    return args + [
        "--at-ns",
        str(WALL + 10 * S),
        "--monotonic-ns",
        str(MONO + 10 * S),
        "--boot-id",
        "fixture-boot",
    ]


def test_cli_is_offline_exclusive_and_rejects_changed_original(evidence, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network used by offline evidence join")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    args = arguments(evidence, tmp_path)
    output = tmp_path / "result.json"
    assert main(args + ["--report", str(output)]) == 2
    original = output.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o600
    assert main(args + ["--report", str(output)]) == 1
    assert output.read_bytes() == original
    (tmp_path / "response").write_bytes(b"changed")
    assert main(args + ["--report", str(tmp_path / "new.json")]) == 1
    assert not (tmp_path / "new.json").exists()
    assert len(list(tmp_path.iterdir())) == 4


def test_two_process_reports_match_and_leave_inputs_unchanged(evidence, tmp_path):
    args = arguments(evidence, tmp_path)
    originals = {p: p.read_bytes() for p in tmp_path.iterdir()}
    results = []
    for n in range(2):
        output = tmp_path / f"review{n}.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.ops.portfolio_joint_admission",
                *args,
                "--report",
                str(output),
            ],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 2, proc.stderr + proc.stdout
        results.append(output.read_bytes())
    assert results[0] == results[1]
    assert all(p.read_bytes() == raw for p, raw in originals.items())


def test_partial_cli_selection_and_mixed_candidate_are_usage_errors(evidence, tmp_path):
    with pytest.raises(SystemExit):
        main(["--bootstrap-plan", "x", "--report", "y"])
    args = arguments(evidence, tmp_path)
    with pytest.raises(SystemExit):
        main(args + ["--candidate", "x", "--candidate-sha256", "0" * 64, "--report", "y"])
    index = args.index("--boot-id")
    with pytest.raises(SystemExit):
        main(args[:index] + ["--report", "y"])


def test_unknown_usage_and_reported_time_stay_separate(evidence):
    plan, rows, _ = evidence
    body = json.dumps(
        {
            "serverTime": 123456789,
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "MINUTE",
                    "intervalNum": 1,
                    "limit": 6000,
                },
                {
                    "rateLimitType": "RAW_REQUESTS",
                    "interval": "MINUTE",
                    "intervalNum": 5,
                    "limit": 300000,
                },
                {"rateLimitType": "ORDERS", "interval": "DAY", "intervalNum": 1, "limit": 160000},
            ],
        }
    ).encode()
    pairs = [
        ["Content-Length", str(len(body))],
        ["X-MBX-USED-WEIGHT-1M", "20"],
        ["Date", "Wed, 16 Sep 2026 09:34:12 GMT"],
    ]
    response = (
        "HTTP/1.1 200 OK\r\n" + "".join(f"{k}: {v}\r\n" for k, v in pairs) + "\r\n"
    ).encode() + body
    rows[8].update(size=len(response), sha256=sha(response))
    rows[9].update(headers=pairs, body_length=len(body), body_sha256=sha(body))
    r = call((plan, rows, response))
    intervals = {row["rate_limit_type"]: row for row in r["interval_reviews"]}
    assert intervals["REQUEST_WEIGHT"]["remaining_scope_reservation"] == 468
    assert intervals["RAW_REQUESTS"]["remaining_scope_reservation"] == 17
    assert intervals["RAW_REQUESTS"]["count"] is None
    assert intervals["ORDERS"]["count"] is None
    assert intervals["ORDERS"]["scope"] == "account"
    assert all(
        row["used_upper_bound"] is None and row["other_clients_upper_bound"] is None
        for row in intervals.values()
    )
    assert r["bootstrap_context"]["reported_server_time_ms"] == 123456789
    assert r["bootstrap_context"]["server_time_interval_ns"] is None
    assert not r["bootstrap_context"]["http_date_is_clock_anchor"]
    assert r["connection_review"] is None
