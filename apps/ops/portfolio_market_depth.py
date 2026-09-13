"""One bounded public BTCUSDT depth probe or explicit historical archive replay.

No key, account endpoint, order client, execution engine, service or fixed-session
writer. Invalid/unfinished probes remain diagnostic failures without retry.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import http.client
import json
import time
from collections import deque
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from nautilus_trader.core.nautilus_pyo3 import WebSocketClient, WebSocketConfig

from apps.strategies_nautilus.portfolio_market_depth import (
    MAX_ARCHIVE,
    MAX_FRAME,
    SECOND,
    STREAM,
    DepthError,
)
from apps.strategies_nautilus.portfolio_market_depth_archive import (
    REQUESTS,
    DepthJournal,
    flags,
    replay_depth,
)
from apps.strategies_nautilus.portfolio_session_transport import private_read, write_private_new
from apps.strategies_nautilus.portfolio_stream import canonical


def clock():
    return time.time_ns(), time.monotonic_ns()


def public_get(path, params):
    """HTTPS direct to the fixed public host; no redirects, proxy discovery or auth."""
    if (path, params) not in [(p, s) for p, s, _ in REQUESTS]:
        raise DepthError("public_get_not_allowlisted")
    connection = http.client.HTTPSConnection("testnet.binance.vision", timeout=10)
    try:
        url = path + ("?" + urlencode(params) if params else "")
        connection.request("GET", url, headers={"User-Agent": "trader-depth-diagnostic-v1"})
        response = connection.getresponse()
        raw = response.read(8 * MAX_FRAME + 1)
        headers = {key.lower(): value for key, value in response.getheaders()}
        if len(raw) > 8 * MAX_FRAME:
            raise DepthError("public_response_oversized")
        return response.status, headers, raw
    finally:
        connection.close()


async def connect_depth(*, handler, ping_handler, post_reconnection):
    return await WebSocketClient.connect(
        loop_=asyncio.get_running_loop(),
        config=WebSocketConfig(url=STREAM, headers=[], heartbeat=None, reconnect_max_attempts=0),
        handler=handler,
        ping_handler=ping_handler,
        post_reconnection=post_reconnection,
    )


async def probe(archive, *, seconds=20, revision=1):
    if type(seconds) is not int or not 1 <= seconds <= 120:
        raise DepthError("bounded_probe_duration_required")
    journal = DepthJournal(archive, epoch=uuid4().hex, clock=clock, revision=revision)
    state, client, pending_pongs = journal.state, None, set()
    reason, accepting, disconnect_attempted = None, True, False
    pings = deque()
    start_mono = state.started[1]
    first_frame = asyncio.Event()

    def mark_connected(received):
        if not state.connected:
            journal.append("connected", received_ns=received[0], monotonic_ns=received[1])

    def fail(exc):
        nonlocal reason
        if reason is None:
            reason = str(exc) if isinstance(exc, DepthError) else "public_depth_transport_failed"
            state.failure = state.failure or reason

    def frame(raw):
        if not accepting or reason:
            return
        try:
            received = clock()
            mark_connected(received)
            if len(raw) > MAX_FRAME:
                raise DepthError("depth_frame_oversized")
            journal.append(
                "depth_frame",
                raw_b64=base64.b64encode(raw).decode(),
                body_sha256=hashlib.sha256(raw).hexdigest(),
                received_ns=received[0],
                monotonic_ns=received[1],
            )
            first_frame.set()
        except Exception as exc:
            fail(exc)
            first_frame.set()

    async def pong(raw):
        try:
            if client is None or not client.is_active():
                raise DepthError("ping_without_active_depth_connection")
            await client.send_pong(raw)
        except Exception as exc:
            fail(exc)

    def ping(raw):
        if not accepting or reason:
            return
        now = clock()[1]
        while pings and now - pings[0] >= SECOND:
            pings.popleft()
        if len(raw) > 125 or len(pings) >= 5:
            fail(DepthError("public_control_message_limit"))
            return
        pings.append(now)
        task = asyncio.create_task(pong(raw))
        pending_pongs.add(task)
        task.add_done_callback(pending_pongs.discard)

    def healthy():
        if reason:
            raise DepthError(reason)
        if client is not None and (
            not client.is_active() or client.is_reconnecting() or client.is_disconnecting()
        ):
            raise DepthError("public_depth_connection_lost")

    async def read():
        healthy()
        index = state.requests
        if index >= len(REQUESTS):
            raise DepthError("public_request_budget_exceeded")
        path, params, _ = REQUESTS[index]
        sent = clock()
        async with asyncio.timeout(10):
            status, headers, raw = await asyncio.to_thread(public_get, path, params)
        # Receipt clock is taken on this owning event loop, preserving archive order.
        journal.append(
            "rest_response",
            path=path,
            params=params,
            sent_ns=sent[0],
            sent_monotonic_ns=sent[1],
            status=status,
            headers={
                k: v for k, v in headers.items() if k in {"x-mbx-used-weight-1m", "retry-after"}
            },
            raw_b64=base64.b64encode(raw).decode(),
            body_sha256=hashlib.sha256(raw).hexdigest(),
        )
        healthy()

    try:
        async with asyncio.timeout(seconds):
            await read()  # initial time sample
            await read()  # symbol metadata and current advertised weight limit
            remaining_bootstrap = 15 - (clock()[1] - start_mono) / SECOND
            if remaining_bootstrap <= 0:
                raise DepthError("depth_bootstrap_deadline")
            async with asyncio.timeout(min(10, remaining_bootstrap)):
                client = await connect_depth(
                    handler=frame,
                    ping_handler=ping,
                    post_reconnection=lambda: fail(DepthError("unexpected_public_reconnect")),
                )
            mark_connected(clock())
            async with asyncio.timeout(max(0.001, 15 - (clock()[1] - start_mono) / SECOND)):
                await first_frame.wait()
            await read()  # one snapshot only, after at least one durable stream event
            await read()  # second time sample
            # Reserve enough time for final sample and shutdown without widening total bounds.
            end_mono = start_mono + max(0, seconds - 2) * SECOND
            while clock()[1] < end_mono:
                healthy()
                journal.append("tick")
                await asyncio.sleep(0.1)
            await read()  # final time sample
            healthy()
        # Intentional bounded close occurs before the completion seal.
        disconnect_attempted = True
        async with asyncio.timeout(5):
            await client.disconnect()
            accepting = False
            if pending_pongs:
                await asyncio.gather(*pending_pongs)
        if reason:
            raise DepthError(reason)
        journal.append("transport_closed")
        journal.append("completed", result=state.summary())
        return {"status": "public_depth_probe_completed", "summary": state.summary(), **flags()}
    except BaseException as exc:
        fail(exc)
        with suppress(Exception):
            journal.append("aborted", reason=reason)
        if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
            raise
        return {
            "status": "public_depth_probe_failed",
            "reason": reason,
            "summary": state.summary(),
            **flags(),
        }
    finally:
        accepting = False
        for task in list(pending_pongs):
            task.cancel()
        if client is not None and not disconnect_attempted and not client.is_closed():
            with suppress(Exception):
                async with asyncio.timeout(5):
                    await client.disconnect()
        journal.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true")
    mode.add_argument("--replay", action="store_true")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument(
        "--revision",
        type=int,
        choices=(1, 2),
        default=1,
        help="Explicit contract selection; v1 remains the default for old archives",
    )
    args = parser.parse_args(argv)
    try:
        if (
            args.report.exists()
            or args.report.is_symlink()
            or args.report.resolve() == args.archive.resolve()
        ):
            raise DepthError("depth_output_must_be_new_and_distinct")
        if not args.report.parent.is_dir():
            raise DepthError("depth_report_parent_required")
        if args.probe:
            if args.archive_sha256 is not None:
                raise DepthError("probe_cannot_select_existing_archive")
            report = asyncio.run(probe(args.archive, seconds=args.seconds, revision=args.revision))
            raw = private_read(args.archive, limit=MAX_ARCHIVE)
            digest = hashlib.sha256(raw).hexdigest()
            report["archive_sha256"] = digest
            if report["status"] == "public_depth_probe_completed":
                replayed = replay_depth(raw, expected_sha256=digest, revision=args.revision)
                if replayed["summary"] != report["summary"]:
                    raise DepthError("immediate_depth_replay_differs")
                report["detached_replay_equal"] = True
        else:
            report = replay_depth(
                private_read(args.archive, limit=MAX_ARCHIVE),
                expected_sha256=args.archive_sha256,
                revision=args.revision,
            )
        output = canonical(report) + b"\n"
        write_private_new(args.report, output)
    except Exception:
        print(json.dumps({"status": "public_depth_review_failed", **flags()}))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "reason": report.get("reason"),
                "archive_sha256": report["archive_sha256"],
                "report_sha256": hashlib.sha256(output).hexdigest(),
                "native_quote_count": report["summary"]["native_quote_count"],
                **flags(),
            },
            sort_keys=True,
        )
    )
    return int(report["status"] == "public_depth_probe_failed")


if __name__ == "__main__":
    raise SystemExit(main())
