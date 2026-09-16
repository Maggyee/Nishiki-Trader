"""Actual local TLS plus permanent scope consumption, with no real venue mode."""

import asyncio
import json
import os
import subprocess
import sys
from contextlib import suppress

import pytest

from apps.strategies_nautilus import portfolio_rest_bootstrap as bootstrap
from apps.strategies_nautilus import portfolio_tls_provenance as tls
from tests.strategies_nautilus.test_portfolio_tls_provenance import (
    BODY,
)
from tests.strategies_nautilus.test_portfolio_tls_provenance import (
    allow_local as allow_local,
)
from tests.strategies_nautilus.test_portfolio_tls_provenance import (
    certificates as certificates,
)


async def scenario(root, certificates, failure=None):
    context, trust = certificates["selected"]
    if failure == "certificate":
        context = certificates["foreign"][0]
    requests = []
    writers = []

    async def peer(reader, writer):
        writers.append(writer)
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            requests.append(request)
            if failure in {"cancel", "timeout"}:
                await reader.read()
                return
            body = BODY if failure != "invalid_rates" else b"{}"
            wire = (
                b"HTTP/1.1 200 OK\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\nX-MBX-USED-WEIGHT-1M: 70\r\n\r\n"
                + body
            )
            if failure == "body_limit":
                wire = b"HTTP/1.1 200 OK\r\nContent-Length: 8388609\r\n\r\n"
            elif failure == "redirect":
                wire = b"HTTP/1.1 302 Found\r\nLocation: https://example.com\r\nContent-Length: 0\r\n\r\n"
            elif failure == "partial":
                wire = wire[:-10]
            writer.write(wire)
            await writer.drain()
            if failure != "partial":
                await reader.read()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

    server = await asyncio.start_server(peer, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    args = {
        "endpoint": f"https://rest.fixture.invalid:{port}/api/v3/exchangeInfo",
        "trust_pem": trust,
        "trust_sha256": tls.digest(trust),
    }
    error = result = None
    try:
        task = asyncio.create_task(bootstrap.capture(root, **args))
        if failure == "cancel":
            async with asyncio.timeout(3):
                while not requests:
                    await asyncio.sleep(0.005)
            task.cancel()
        try:
            result = await task
        except (Exception, asyncio.CancelledError) as exc:
            error = exc
        with pytest.raises(FileExistsError):
            await bootstrap.capture(root, **args)
    finally:
        server.close()
        await server.wait_closed()
        for writer in writers:
            writer.close()
    return result, error, requests


def test_one_get_rates_and_two_fresh_replays(tmp_path, certificates, allow_local):
    result, error, requests = asyncio.run(scenario(tmp_path, certificates))
    assert error is None
    assert len(requests) == len(allow_local) == 1
    assert requests[0].startswith(b"GET /api/v3/exchangeInfo HTTP/1.1\r\n")
    assert b"X-MBX-APIKEY" not in requests[0] and b"Authorization" not in requests[0]
    assert result["rates"]["rates"][0]["count"] == 70
    assert not result["pre_request_capacity_verified"] and not result["network_admitted"]
    directory = tmp_path / bootstrap.SCOPE
    script = "import json,sys; from apps.strategies_nautilus.portfolio_rest_bootstrap import review; print(json.dumps(review(sys.argv[1],expected_sha256=sys.argv[2]),sort_keys=True))"
    reports = [
        json.loads(
            subprocess.check_output(
                [sys.executable, "-c", script, str(directory), result["archive_sha256"]]
            )
        )
        for _ in range(2)
    ]
    assert reports == [result, result]
    assert sum(path.stat().st_size for path in directory.iterdir()) < bootstrap.ARCHIVE_LIMIT


@pytest.mark.parametrize(
    "failure", ["certificate", "body_limit", "redirect", "partial", "cancel", "invalid_rates"]
)
def test_failed_attempt_cannot_reopen_or_retry(tmp_path, certificates, allow_local, failure):
    result, error, requests = asyncio.run(scenario(tmp_path, certificates, failure))
    assert result is None and error is not None
    assert len(allow_local) == 1 and len(requests) <= 1
    directory = tmp_path / bootstrap.SCOPE
    rows = [json.loads(line) for line in (directory / "capture.jsonl").read_bytes().splitlines()]
    assert rows[0]["kind"] == "prepared"
    assert rows[-1]["kind"] == ("completed" if failure == "invalid_rates" else "aborted")
    with pytest.raises(ValueError):
        bootstrap.review(
            directory, expected_sha256=tls.digest((directory / "capture.jsonl").read_bytes())
        )


def test_real_authority_is_rejected_before_consumption(tmp_path, certificates, allow_local):
    trust = certificates["selected"][1]
    with pytest.raises(tls.ProvenanceError):
        asyncio.run(
            bootstrap.capture(
                tmp_path,
                endpoint="https://testnet.binance.vision/api/v3/exchangeInfo",
                trust_pem=trust,
                trust_sha256=tls.digest(trust),
            )
        )
    assert not list(tmp_path.iterdir()) and not allow_local


def test_scope_fsync_failure_never_opens_socket_and_cannot_retry(
    tmp_path, certificates, monkeypatch
):
    def fail(path):
        raise OSError("fsync failed")

    monkeypatch.setattr(bootstrap, "_sync", fail)

    async def forbidden(*args, **kwargs):
        pytest.fail("network before durable preparation")

    monkeypatch.setattr(tls, "capture_loopback_tls", forbidden)
    trust = certificates["selected"][1]
    args = dict(
        endpoint="https://rest.fixture.invalid:1234/api/v3/exchangeInfo",
        trust_pem=trust,
        trust_sha256=tls.digest(trust),
    )
    with pytest.raises(OSError):
        asyncio.run(bootstrap.capture(tmp_path, **args))
    assert (tmp_path / bootstrap.SCOPE).is_dir()
    with pytest.raises(FileExistsError):
        asyncio.run(bootstrap.capture(tmp_path, **args))


def test_incident_reserve_survives_archive_exhaustion(tmp_path):
    path = tmp_path / "journal"
    journal = tls._Journal(path, limit=8192, reserve=4096)
    try:
        journal.append("prepared", payload="x" * 3500)
        with pytest.raises(tls.ProvenanceError):
            journal.append("response_chunk", payload="x" * 600)
        journal.append("aborted", reason="ProvenanceError")
    finally:
        os.close(journal.fd)
    assert path.stat().st_size <= 8192
    assert json.loads(path.read_bytes().splitlines()[-1])["kind"] == "aborted"


@pytest.mark.parametrize(
    "limits",
    [
        {"max_body": 0},
        {"max_body": True},
        {"max_body": tls.MAX_BODY + 1},
        {"max_archive": 4095},
        {"incident_reserve": 4097},
        {"close_timeout": 0},
        {"close_timeout": 6},
    ],
)
def test_invalid_limits_fail_before_archive(tmp_path, certificates, limits):
    trust = certificates["selected"][1]
    with pytest.raises(tls.ProvenanceError):
        asyncio.run(
            tls.capture_loopback_tls(
                tmp_path / "capture",
                endpoint="https://rest.fixture.invalid:1234/api/v3/exchangeInfo",
                role="rest",
                trust_pem=trust,
                trust_sha256=tls.digest(trust),
                **limits,
            )
        )
    assert not list(tmp_path.iterdir())


def test_abrupt_process_death_consumes_scope_without_retry(tmp_path, certificates):
    async def exercise():
        context, trust = certificates["selected"]
        seen = asyncio.Event()
        requests = []

        async def peer(reader, writer):
            try:
                requests.append(await reader.readuntil(b"\r\n\r\n"))
                seen.set()
                await reader.read()
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                with suppress(ConnectionError):
                    await writer.wait_closed()

        server = await asyncio.start_server(peer, "127.0.0.1", 0, ssl=context)
        port = server.sockets[0].getsockname()[1]
        trust_path = tmp_path / "trust.pem"
        trust_path.write_bytes(trust)
        script = "import asyncio,sys; from pathlib import Path; from apps.strategies_nautilus.portfolio_rest_bootstrap import capture; from apps.strategies_nautilus.portfolio_tls_provenance import digest; trust=Path(sys.argv[2]).read_bytes(); asyncio.run(capture(Path(sys.argv[1]),endpoint=sys.argv[3],trust_pem=trust,trust_sha256=digest(trust)))"
        args = [
            sys.executable,
            "-c",
            script,
            str(tmp_path),
            str(trust_path),
            f"https://rest.fixture.invalid:{port}/api/v3/exchangeInfo",
        ]
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            async with asyncio.timeout(5):
                await seen.wait()
            process.kill()
            await process.communicate()
            directory = tmp_path / bootstrap.SCOPE
            path = directory / "capture.jsonl"
            original = path.read_bytes()
            kinds = [json.loads(line)["kind"] for line in original.splitlines()]
            assert (
                "request_prepared" in kinds and "completed" not in kinds and "aborted" not in kinds
            )
            with pytest.raises(tls.ProvenanceError):
                bootstrap.review(directory, expected_sha256=tls.digest(original))
            fresh = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            async with asyncio.timeout(5):
                _, err = await fresh.communicate()
            assert fresh.returncode != 0 and b"FileExistsError" in err
            assert len(requests) == 1 and path.read_bytes() == original
        finally:
            if process.returncode is None:
                process.kill()
                await process.communicate()
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_timeout_keeps_consumed_scope(tmp_path, certificates, allow_local, monkeypatch):
    capture = tls.capture_loopback_tls

    async def shorter(*args, **kwargs):
        kwargs["timeout"] = 0.05
        return await capture(*args, **kwargs)

    monkeypatch.setattr(tls, "capture_loopback_tls", shorter)
    result, error, requests = asyncio.run(scenario(tmp_path, certificates, "timeout"))
    assert result is None and isinstance(error, TimeoutError)
    assert len(allow_local) == len(requests) == 1
    path = tmp_path / bootstrap.SCOPE / "capture.jsonl"
    assert json.loads(path.read_bytes().splitlines()[-1])["kind"] == "aborted"
