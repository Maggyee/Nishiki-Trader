from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.ops.portfolio_testnet_observe import main, observe_sessions, run
from apps.strategies_nautilus.portfolio_stream import StreamError, bind_source, canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.portfolio_testnet_observation import (
    TestnetObservationJournal,
    account_balances,
    collect_testnet_observation,
    replay_testnet_observation,
    select_initial_observation,
)
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS

SELECTED = "a" * 64


def account():
    return {
        "uid": 123,
        "accountType": "SPOT",
        "canTrade": True,
        "balances": [
            {"asset": name, "free": "1.23456789", "locked": "0.00000001"}
            for name in ["BTC", "USDT", "币安", *[f"ASSET{i}" for i in range(499)]]
        ],
    }


@pytest.fixture
def setup(tmp_path):
    clock = SimpleNamespace(now=BASE_NS)
    http = SimpleNamespace(base_url=TESTNET_REST, api_key="synthetic-key", calls=[])
    binding = bind_source(http, "123")
    path = tmp_path / "journal.jsonl"
    journal = TestnetObservationJournal(path, binding, clock_ns=lambda: clock.now)
    journal.subscribed(7, binding)
    http.bodies = [account(), [], [], account()]

    async def sign(method, path, *, payload):
        assert method == HttpMethod.GET
        assert set(payload) <= {"timestamp", "recvWindow", "omitZeroBalances"}
        http.calls.append((path, payload))
        clock.now += 1_000_000
        return canonical(http.bodies[(len(http.calls) - 1) % 4])

    http.sign_request = sign
    yield http, journal, path, clock
    journal.close()


def collect(setup):
    http, journal, _, _ = setup
    return asyncio.run(collect_testnet_observation(http, journal, selection_sha256=SELECTED))


def replay(setup, result, raw=None, **kwargs):
    _, journal, path, _ = setup
    raw = path.read_bytes() if raw is None else raw
    params = dict(
        source=journal.binding,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        collection_id=result["collection_id"],
        selection_sha256=SELECTED,
    )
    return replay_testnet_observation(raw, **(params | kwargs))


def rechain(rows):
    previous, lines = "0" * 64, []
    for seq, row in enumerate(rows):
        row.pop("sha256", None)
        row.update(seq=seq, previous=previous)
        previous = hashlib.sha256(canonical(row)).hexdigest()
        lines.append(canonical({**row, "sha256": previous}) + b"\n")
    return b"".join(lines)


def event(journal, clock, kind="outboundAccountPosition"):
    return canonical(
        {
            "subscriptionId": journal.subscription_id,
            "event": {
                "e": kind,
                "E": clock.now // 1_000_000,
                "B": [{"a": "币安", "f": "1", "l": "0"}],
            },
        }
    )


def test_all_assets_and_account_wide_orders_preserved_and_replayed(setup):
    http, journal, path, _ = setup
    http.bodies[1:3] = [[{"symbol": "币安USDT", "orderId": 77, "status": "NEW"}]] * 2
    result = collect(setup)
    assert result["assets_recorded"] == result["nonzero_assets"] == 502
    assert result["open_orders_recorded"] == 1
    assert result["api_trading_enabled"] is None
    for key in (
        "runtime_ready",
        "api_key_restrictions_verified",
        "independent_uid_verified",
        "baseline_qualified",
        "atomic_revision_verified",
        "downtime_history_complete",
    ):
        assert result[key] is False
    assert "stream_fence" not in result
    assert all("symbol" not in payload for _, payload in http.calls)
    assert not any("sapi" in path for path, _ in http.calls)
    journal.disconnect()
    assert replay(setup, result) == result
    assert http.api_key.encode() not in path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "change",
    ["duplicate", "negative", "nan", "float", "uid", "canTrade", "missing", "invalid_name"],
)
def test_invalid_full_account_rejected(setup, change):
    body = setup[0].bodies[0]
    if change == "duplicate":
        body["balances"].append(body["balances"][0])
    elif change in {"negative", "nan", "float"}:
        body["balances"][0]["free"] = {"negative": "-1", "nan": "NaN", "float": 1.2}[change]
    elif change == "uid":
        body["uid"] = True
    elif change == "canTrade":
        body["canTrade"] = 1
    elif change == "missing":
        body["balances"][0].pop("locked")
    else:
        body["balances"][0]["asset"] = "bad\nname"
    with pytest.raises(ValueError):
        collect(setup)
    assert setup[1]._active_collection is None
    assert json.loads(setup[2].read_bytes().splitlines()[-1])["kind"] == "rest_aborted"


@pytest.mark.parametrize(
    "change", ["asset_removed", "balance", "order", "duplicate_order", "order_bool", "uid"]
)
def test_rest_drift_and_bad_orders_fail_without_seal(setup, change):
    http = setup[0]
    if change == "asset_removed":
        http.bodies[3]["balances"].pop()
    elif change == "balance":
        http.bodies[3]["balances"][0]["locked"] = "2"
    elif change == "uid":
        http.bodies[3]["uid"] = 124
    elif change == "order":
        http.bodies[2] = [{"symbol": "BTCUSDT", "orderId": 5}]
    elif change == "duplicate_order":
        http.bodies[1:3] = [[{"symbol": "BTCUSDT", "orderId": 5}] * 2] * 2
    else:
        http.bodies[1:3] = [[{"symbol": "BTCUSDT", "orderId": True}]] * 2
    with pytest.raises(StreamError):
        collect(setup)
    assert b"testnet_observation_completed" not in setup[2].read_bytes()


@pytest.mark.parametrize(
    "kind",
    [
        "outboundAccountPosition",
        "balanceUpdate",
        "executionReport",
        "externalLockUpdate",
        "listStatus",
        "eventStreamTerminated",
        "unknown",
    ],
)
def test_raw_events_are_retained_and_invalidate_fences(setup, kind):
    _, journal, path, clock = setup
    fence = journal.fence()
    raw = event(journal, clock, kind)
    if kind in {"unknown", "eventStreamTerminated"}:
        with pytest.raises(StreamError):
            journal.observe(raw)
        assert not journal.connected
    else:
        journal.observe(raw)
        journal.observe(raw)  # no invented deduplication or financial-event qualification
        assert journal.revision == fence.revision + 2
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    assert next(row for row in rows if row["kind"] == "testnet_event")["raw"] == raw.decode()
    with pytest.raises(StreamError):
        journal.assert_fence(fence)


@pytest.mark.parametrize("change", ["event", "disconnect", "key", "clock", "cancel", "timeout"])
def test_interrupted_collection_aborts_and_explicit_retry_can_succeed(setup, change):
    http, journal, _, clock = setup
    sign = http.sign_request

    async def changed(*args, **kwargs):
        raw = await sign(*args, **kwargs)
        if change == "event":
            journal.observe(event(journal, clock))
        elif change == "disconnect":
            journal.disconnect()
        elif change == "key":
            http.api_key = "different-key"
        elif change == "clock":
            clock.now -= 2_000_000
        elif change == "cancel":
            raise asyncio.CancelledError
        else:
            raise TimeoutError
        return raw

    http.sign_request = changed
    with pytest.raises((StreamError, asyncio.CancelledError, TimeoutError)):
        collect(setup)
    assert journal._active_collection is None
    http.api_key, http.sign_request = "synthetic-key", sign
    http.calls.clear()
    clock.now = BASE_NS + 10_000_000
    if not journal.connected:
        journal.subscribed(8, journal.binding)
    result = collect(setup)
    # Clock-regressing archives intentionally fail global historical validation.
    if change != "clock":
        assert replay(setup, result) == result


def test_observation_profile_cannot_seal_strict_recovery_evidence(setup):
    journal = setup[1]
    with pytest.raises(StreamError):
        journal.begin_collection(journal.fence(), {"uid": "123"}, BASE_NS)
    with pytest.raises(StreamError):
        journal.record_collection(journal.fence(), [])


@pytest.mark.parametrize(
    "change",
    [
        "digest",
        "tail",
        "truncate",
        "source",
        "selection",
        "epoch",
        "event",
        "response_time",
        "start_bool",
        "row_time",
        "params",
        "raw",
        "seal",
        "reuse",
    ],
)
def test_archive_tamper_or_interruption_cannot_replay(setup, change):
    result = collect(setup)
    raw = setup[2].read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    responses = [row for row in rows if row["kind"] == "rest_response"]
    start = next(row for row in rows if row["kind"] == "rest_started")
    kwargs = {}
    if change == "digest":
        kwargs["expected_sha256"] = "0" * 64
    elif change == "tail":
        raw = raw[:-1]
    elif change == "truncate":
        raw = b"\n".join(raw.splitlines()[:-1]) + b"\n"
    elif change == "source":
        kwargs["source"] = replace(setup[1].binding, account_uid="124")
    elif change == "selection":
        kwargs["selection_sha256"] = "b" * 64
    else:
        if change == "epoch":
            responses[0]["epoch"] = "different"
        elif change == "event":
            responses[0]["kind"] = "testnet_event"
        elif change == "response_time":
            responses[1]["response_ns"] = responses[0]["response_ns"] - 1
        elif change == "start_bool":
            start["started_ns"] = True
        elif change == "row_time":
            responses[1]["received_ns"] = responses[0]["received_ns"] - 1
        elif change == "params":
            responses[1]["params"] = {"symbol": "BTCUSDT"}
        elif change == "raw":
            responses[0]["raw"] = "{}"
        elif change == "seal":
            rows[-1]["response_sha256"] = []
        else:
            rows.append(copy.deepcopy(rows[-1]))
        raw = rechain(rows)
    with pytest.raises(StreamError):
        replay(setup, result, raw, **kwargs)


def test_selected_initial_observation_binds_observed_uid_only(setup):
    http, journal, _, _ = setup
    body = canonical(account()).decode()
    wrapped = {
        "schema_version": "portfolio.testnet_initial_account_observation.v1",
        "endpoint": TESTNET_REST,
        "path": "/api/v3/account",
        "key_sha256": journal.binding.key_sha256,
        "response_body": body,
        "response_sha256": hashlib.sha256(body.encode()).hexdigest(),
    }
    raw = canonical(wrapped)
    digest = hashlib.sha256(raw).hexdigest()
    assert select_initial_observation(raw, digest, http) == journal.binding
    http.api_key = "different"
    with pytest.raises(StreamError):
        select_initial_observation(raw, digest, http)
    with pytest.raises(StreamError):
        select_initial_observation(raw, "0" * 64, http)
    assert len(account_balances(account(), "123")) == 502


def test_bounded_sessions_reconnect_and_replay_all_observations(setup):
    http, journal, _, _ = setup

    class Stream:
        async def start(self):
            journal.subscribed(7, journal.binding)

        async def ping(self):
            journal.transport_alive()

        async def disconnect(self):
            journal.disconnect()

    results, epochs = asyncio.run(
        observe_sessions(
            http,
            Stream(),
            journal,
            selection_sha256=SELECTED,
            interval_seconds=0.001,
        )
    )
    assert len(set(epochs)) == 2
    assert len(results) == 4
    assert len(http.calls) == 16
    assert not journal.connected
    for result in results:
        assert replay(setup, result) == result


def test_cli_failure_does_not_echo_private_exception(tmp_path, monkeypatch, capsys):
    async def failed(args):
        raise ValueError("private-key-material")

    monkeypatch.setattr("apps.ops.portfolio_testnet_observe.run", failed)
    assert (
        main(
            [
                "--credentials",
                str(tmp_path / "env"),
                "--selection",
                str(tmp_path / "input"),
                "--selection-sha256",
                SELECTED,
                "--archive",
                str(tmp_path / "new"),
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "private-key-material" not in output
    assert json.loads(output)["runtime_ready"] is False


@pytest.mark.parametrize("mode", ["success", "existing_archive", "failed_subscription"])
def test_ops_run_owns_private_archive_and_closes_on_failure(setup, tmp_path, monkeypatch, mode):
    http = setup[0]
    owned = []
    body = canonical(account()).decode()
    initial = canonical(
        {
            "schema_version": "portfolio.testnet_initial_account_observation.v1",
            "endpoint": TESTNET_REST,
            "path": "/api/v3/account",
            "key_sha256": setup[1].binding.key_sha256,
            "response_body": body,
            "response_sha256": hashlib.sha256(body.encode()).hexdigest(),
        }
    )
    selection = tmp_path / "initial.json"
    selection.write_bytes(initial)
    args = SimpleNamespace(
        credentials=tmp_path / "unused.env",
        selection=selection,
        selection_sha256=hashlib.sha256(initial).hexdigest(),
        archive=tmp_path / "observations.jsonl",
    )

    class Stream:
        def __init__(self, journal):
            self.journal, self.closed = journal, False

        async def start(self):
            if mode == "failed_subscription":
                raise StreamError("subscription failed")
            self.journal.subscribed(7, self.journal.binding)

        async def ping(self):
            self.journal.transport_alive()

        async def disconnect(self):
            self.closed = True
            self.journal.disconnect()

    def clients(*, journal, **kwargs):
        owned.append(Stream(journal))
        return http, owned[-1]

    async def fast_sessions(*args, **kwargs):
        return await observe_sessions(*args, **kwargs, interval_seconds=0.001)

    credentials = SimpleNamespace(create_http_client=lambda clock: http, create_clients=clients)
    monkeypatch.setattr(
        "apps.ops.portfolio_testnet_observe.load_testnet_ed25519_credentials",
        lambda path: credentials,
    )
    monkeypatch.setattr("apps.ops.portfolio_testnet_observe.observe_sessions", fast_sessions)
    if mode == "existing_archive":
        args.archive.write_bytes(b"retained-evidence")
        with pytest.raises(FileExistsError):
            asyncio.run(run(args))
        assert args.archive.read_bytes() == b"retained-evidence"
        assert not owned and not http.calls
        return
    if mode == "failed_subscription":
        with pytest.raises(StreamError):
            asyncio.run(run(args))
        assert not http.calls
    else:
        result = asyncio.run(run(args))
        assert result["local_replay_verified"] and result["explicit_reconnect_verified"]
        assert result["account_events_observed"] == 0
        assert result["health_receipts"] == 6
        assert result["global_stream_continuity_verified"] is False
        assert result["adapter_process_recovery_verified"] is False
    assert owned[0].closed and owned[0].journal._file.closed
    assert args.archive.stat().st_mode & 0o777 == 0o600
