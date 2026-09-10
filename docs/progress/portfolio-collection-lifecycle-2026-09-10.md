# Account collection interruption and concurrency — 2026-09-10

Status: fixed and verified locally. This follows
[raw account response persistence](portfolio-account-archive-2026-09-10.md).
No account credentials, external private endpoints or execution runners were used.

## Reproduced problem

Two independent `BinanceReadOnlyAccountCollector` objects could share one
`UserStreamJournal`, begin concurrent collections and interleave their receipt
records. Because REST writes do not advance the account-event revision, both
calls could report success. Offline replay correctly rejected a selected collection
containing another collection's records. The producer and reviewer therefore
disagreed about which recorded collection was usable.

A deterministic regression pauses the first collector at its first request and
starts a second collector against the same journal. Before the fix the second
call returned successfully; the new expectation that it be refused failed. After
the fix the second call sends zero requests and the first collection replays
exactly from its retained evidence.

The collector also previously checked its overall 60-second age only after the
last read. Up to 69 separately bounded reads could consume much more than a
minute before rejection, and a regressing wall clock was not rejected consistently.

## Resulting behavior

- The journal owns one active collection ID. A second begin is refused before any
  request or new journal record, even when callers use different collector objects.
  Responses and successful completion must match the active ID.
- Successful completion releases ownership only after its marker is flushed and
  fsynced. Failure, cancellation or timeout invokes synchronous cleanup: append
  `rest_aborted` for that collection, then release its ownership. The abort marker
  contains no exception text, response body, credential or signature.
- A failed abort write leaves the journal blocked through its existing persistence
  failure mechanism. A new collection cannot silently bypass failed durability.
  An abrupt process exit may still leave no abort marker; the existing absence of
  a completed collection and fresh-subscription requirement handle that case.
- `asyncio.timeout(60)` bounds the entire asynchronous collection, including its
  requests, for collectors with or without a journal. Per-request limits remain.
  Synchronous JSON work and fsync cannot be preempted by an event-loop deadline;
  this is not a guarantee against an indefinitely stalled storage device.
- Before each request, and after each response, the collector checks integer,
  non-regressing receipt time within its existing 60-second freshness window.
  Source and stream fence are rechecked before every stream-bound request. A key
  rotation detected after one response prevents the next signed request.
- After successful cleanup, callers may explicitly start a new collection. After
  a disconnect they must also establish a fresh subscription. No automatic retry,
  resubmission, reconnect or trading restart is introduced.

Offline replay already rejects an abort or any other interruption before a
completion marker. It can still select a later successful collection from the same
archive without retroactively accepting the failed one. Historical results have
no current stream fence and cannot satisfy the native adapter recovery gate.

## Verification

Twelve new tests cover shared-journal concurrency; cancellation, timeout, response
failure and disconnect followed by a successful independent collection; standalone
collector timeout; clock regression, expiry and invalid clock types; key rotation;
and abort persistence failure. The successful result after each recoverable failure
is replayed through the existing archive reviewer and compared with its original
`AccountEvidence`. Failed collection IDs remain rejected.

The related collector, journal, native read-only transport and archive suite passes
**130 tests**. Tests use synthetic account bodies, controlled asynchronous waits,
and the existing loopback transport checks. No real account source or Binance
HTTP/WS connection is qualified by these results.

Full offline regression: **2,194 passed**, 12 PostgreSQL integration tests
deselected without a dedicated integration DSN. Ruff, registry and whitespace
checks pass.

```bash
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_account_collector.py tests/strategies_nautilus/test_portfolio_account_archive.py tests/strategies_nautilus/test_portfolio_stream.py tests/strategies_nautilus/test_portfolio_user_stream.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
git diff --check
```

Runtime policies, SignalEvent v1, native execution ownership, strategy checkpoints,
risk latches, account/price coverage claims and the 5% rule remain unchanged.
The actual environment, credential variable names/configuration path, expected UID
and independently evidenced account baseline remain missing inputs for the next
real read-only acceptance. No secret values should be sent in chat.
