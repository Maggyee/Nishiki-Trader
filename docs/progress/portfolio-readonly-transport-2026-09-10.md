# Native read-only account transport — 2026-09-10

Status: **project-owned read-only transport implemented; native WebSocket I/O
verified against a local peer**. This is the next increment after
[source/stream/adapter acceptance](portfolio-source-stream-adapter-2026-09-10.md).
No real Binance account, production WebSocket, credential file or private endpoint
was accessed. Original progress records remain immutable.

## Native interface findings

The inspected Binance Spot specification supports
`userDataStream.subscribe.signature` without `session.logon`. The latter supports
Ed25519 session authentication only; it is not the HMAC subscription path.
Nautilus 1.226.0's generic user-stream client calls `session.logon`, strips the
subscription envelope before delivery and handles termination through automatic
resubscription. Its request logger includes signed parameters at DEBUG. Its HTTP
client also logs the signed query string at DEBUG. Those defaults do not satisfy
this dedicated account observer's evidence and logging boundaries.

The new `portfolio_user_stream.ReadOnlyBinanceUserStream` subclasses the native
user-stream client to retain native signing, and uses the installed Rust
`WebSocketClient` for I/O. Project-owned overrides implement signed subscription,
raw envelope handling, request validation and explicit recovery. Upstream source
and installed packages are untouched. HMAC signatures are independently checked
in tests; inherited Ed25519 support has not received equivalent transport acceptance.

## Read-only transport behavior

- REST and WS endpoints are paired explicitly for production or Spot testnet.
  There is no caller-selected arbitrary host or environment fallback. Expected UID
  and API-key fingerprint remain bound to the explicitly configured REST client.
- Only signed subscription, `ping` and user-stream unsubscribe requests may be
  sent. No session login, order endpoint, execution client or trading command is
  enabled. Subscription confirmation requires the outstanding request ID, integer
  status 200 and a nonnegative integer subscription ID.
- The confirmation updates the durable journal synchronously before the next
  event callback. Complete raw event envelopes reach the journal. An event before
  confirmation, unknown response, malformed frame, wrong subscription, termination
  or persistence failure invalidates the transport and wakes pending requests.
- One subscription may be pending/active. Request send and response waits are
  bounded together at ten seconds; cancellation and timeout clear waiters and
  invalidate the session. Connection and shutdown are bounded as well.
- Every journal fence checks the native socket state and current source binding,
  in addition to time/epoch/revision. An explicit application `ping` refreshes
  observed transport health without changing account revision. A task owned by
  the stream checks health at most every twenty seconds and stops on disconnect.
  This is a caller-owned connection task, not a new service or schedule.
- Native socket reconnection invalidates the subscription; it cannot automatically
  reauthenticate or qualify account state. Close and explicit start create a new
  subscription epoch. Old connection callbacks cannot mutate the new epoch.
- `collect(anchor)` runs a health check, invokes the signed account collector with
  this journal and rechecks its fence before returning. Events, key changes or
  loss of transport during REST collection reject the result. Callers must still
  recheck the fence immediately before using it.

`portfolio_account_collector.BinanceAccountReadOnlyHttpClient` is an explicit
account-only extension of the native HTTP client. Native request signing and Rust
HTTP transport remain in use. The send override admits only GET requests to the
five existing account/permissions/orders/trades paths on the two official hosts.
It avoids the upstream signed-URL debug statement, bounds requests and returns
generic errors without private response text. The new WS observer requires this
HTTP extension. Existing collectors/runners keep their previous defaults.

GET-only request enforcement does not prove a key has no other permissions.
The collector still requires reading permission and reports actual Spot trading
permission. Testnet support for the mandatory SAPI permission endpoint remains
unqualified; missing endpoints fail closed and never trigger production fallback.

## Integration entrypoint

The owner supplies an existing, explicitly selected account configuration and
independent baseline. No credential discovery, environment-variable fallback,
order submission, promotion or automatic trading restart is performed here.

```python
import asyncio
from pathlib import Path

from nautilus_trader.common.component import LiveClock
from apps.strategies_nautilus.portfolio_account_collector import BinanceAccountReadOnlyHttpClient
from apps.strategies_nautilus.portfolio_stream import UserStreamJournal, bind_source
from apps.strategies_nautilus.portfolio_user_stream import ReadOnlyBinanceUserStream

async def observe_account(api_key, api_secret, rest_endpoint, anchor, private_archive: Path):
    clock = LiveClock()
    http = BinanceAccountReadOnlyHttpClient(clock, api_key, api_secret, rest_endpoint)
    journal = UserStreamJournal(
        private_archive, bind_source(http, anchor.venue_uid), clock_ns=clock.timestamp_ns,
    )
    stream = None
    try:
        stream = ReadOnlyBinanceUserStream(
            http, api_secret=api_secret, journal=journal, clock=clock,
            loop=asyncio.get_running_loop(),
        )
        await stream.start()
        captured = await stream.collect(anchor)
        journal.assert_fence(captured.stream_fence)
        # Persist/review captured.evidence locally; compare it with native state
        # using the existing account gate while this connection remains owned.
        # atomic_revision_verified remains False; this is not a runtime permit.
    finally:
        try:
            if stream is not None:
                await stream.disconnect()
        finally:
            journal.close()
```

Archive paths must be private, ignored local data; no secret values or signed
requests belong in logs or commits. Closing the connection invalidates its fence.
Persisted response bodies are evidence for later review, not reusable fresh
connection approval. The account's actual starting balance/time must be provided;
the provisional 500 USDT planning amount cannot substitute for an account baseline.

## Acceptance and remaining scope

42 new tests pass; the source/collector/transport regression passes 87 tests.
Tests cover independently verified native HMAC signatures, response binding,
immediate first event, early unbound event, duplicate pending subscriptions,
method/path rejection, persistence failure, request cancellation/timeout, safe
error handling, active socket checks, obsolete callbacks, explicit new epochs,
source changes and REST/event races. A logger trap verifies that account HTTP
requests do not reach the upstream signed-URL debug path.

Two tests use an actual stdlib local WebSocket peer and the real Nautilus Rust
client: signed subscription plus immediate account event and ping; then peer
connection loss invalidating a previously usable fence. Test-only redirection
changes the native dial target to loopback; no external request is sent. This
exercises actual framing/socket callbacks, not Binance TLS, credentials, endpoint
availability, account identity, or exchange recovery after a process crash.

Full offline suite: **2,086 passed**, 12 Postgres tests deselected without a
dedicated integration DSN. Ruff, registry and whitespace checks pass.

```bash
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_user_stream.py tests/strategies_nautilus/test_portfolio_stream.py tests/strategies_nautilus/test_portfolio_account_collector.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
git diff --check
```

Next: supply the actual environment, existing credential variable names/config
path, expected UID and independent account baseline; exercise private account
source/permission qualification and a bounded real stream observation. Then join
independent downtime history and native adapter reconciliation to process recovery.
Local receipts still cannot prove global gap-free delivery; disconnect detection
is bounded by observed native socket/health state. Atomic account admission,
downtime risk-history coverage and real adapter process recovery remain blocked.
No execution runner, SourcePolicy, 5% runtime loss rule, SignalEvent v1, schedule,
allocation or promotion changed.

References: [Spot WebSocket API](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-api.md),
[user stream specification](https://github.com/binance/binance-spot-api-docs/blob/master/user-data-stream.md),
installed native `adapters/binance/websocket/user.py` and `http/client.py` (read only).
