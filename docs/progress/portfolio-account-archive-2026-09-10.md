# Raw account response archive and offline replay — 2026-09-10

Status: implemented for the existing read-only account collector when a user-stream
journal is attached. Previously the journal retained response hashes without the
corresponding REST bodies. A process exit therefore left insufficient evidence to
reproduce that collection from its journal alone. This increment retains the
original responses and reuses the collector to validate them in a fresh process.
No real Binance account, credential configuration or external network was accessed.

## Persistence and failure behavior

Each collection starts with a unique `collection_id`, the explicitly supplied
account anchor and start time. Each returned UTF-8 REST response that passes the
current fence and size checks is written to the source-bound hash chain before
JSON parsing. The receipt records the
endpoint path, unsigned query selectors, exact response body, response SHA256 and
receipt time. Signed query parameters, authentication headers, API keys and secrets
are not copied into the journal. Native signing may mutate its payload; the archived
selectors are a separate copy. These private account bodies belong only in ignored
local archives, not application logs or commits.

Each write flushes and fsyncs before returning. Opening the journal also fsyncs its
parent directory to retain a newly created filename. New files use mode 0600 and
the existing exclusive writer lock. A successful collection writes its completion
marker only after the original permission, UID, pagination, repeated-read and
source/fence checks. The returned `CollectedAccount` carries the selection ID.
An invalid JSON response can remain available for incident inspection but cannot
produce a completed collection. Disconnects, persistence failures and cancellation
cannot turn a partial record set into a successful one. Historical hash-only records
remain readable by the journal but are insufficient for this new replay operation.

This adds archive writes to the opt-in read-only collector; no execution runner,
order handling, SignalEvent v1, SourcePolicy, risk latch or runtime policy changes.
The existing collector without a journal retains its non-durable behavior.

## Explicit local replay

`portfolio_account_archive.replay_account_collection` requires the selected closed
archive bytes and expected whole-file SHA256, collection ID, `SourceBinding`, and
independently selected `AccountAnchor`. It checks the complete record hash chain,
source equality, selected baseline, subscription epoch, matching response hashes,
ordered receipts, completion marker and time bounds. Any intervening stream event,
disconnect, restart or overlapping collection inside the selected collection is
rejected. Callers should collect serially on the transport's owning event loop.

A local replay client supplies the recorded responses to the existing
`BinanceReadOnlyAccountCollector`. It creates no HTTP or WebSocket transport and
does not sign requests. The same collector rechecks reading permission, trading
permission shape, expected UID, account-wide open orders, ordered bounded history
pages, cursor progression, stable before/after account reads and freshness bounds.
Every requested path and unsigned selector must match the next retained receipt;
all receipts and completion hashes must be consumed exactly.

Replay is limited to 64 MiB per selected archive and at most 69 response receipts
per collection (five fixed reads plus two histories of at most 32 pages each).
Collection-time receipts have an 8 MiB raw-body bound. Oversized or truncated inputs
fail; no truncation, rotation or repair is performed automatically.

The expected whole-file hash detects changes, including removal of an entire final
record, relative to the chosen archived copy. Computing a new hash after suspected
loss cannot establish that the missing data never existed. Hashes and local source
metadata do not independently authenticate Binance or prove gap-free delivery.

```bash
.venv/bin/python -m apps.ops.portfolio_account_archive_check \
  data/account-observation.jsonl \
  --sha256 <selected-closed-archive-sha256> \
  --collection-id <returned-collection-id> \
  --source-binding data/account-source-binding.json \
  --anchor data/account-anchor.json
```

The source file has `endpoint`, `account_uid`, `key_sha256`; no secret values.
The anchor file has `venue_uid`, `native_account_id`, integer `start_ns`, and decimal
strings `quote` and `base`. It must describe an independently qualified positive,
flat dedicated-account baseline. The provisional 500 USDT planning budget cannot
substitute for real starting equity. Existing archives must be selected explicitly;
the CLI does not discover credentials or pick an account.

The CLI prints only hashes, selection, timestamps, receipt count and recorded trading
permission. Exit 0 means historical collection reproduction, not a restart permit.
Exit 2 means invalid input or failed replay. Input files are unchanged. All summaries
retain `runtime_ready=false`, `real_account_verified=false`,
`atomic_revision_verified=false`, and `downtime_history_complete=false`.

The Python result exposes the reproduced `AccountEvidence` for detached native
comparison. Its `stream_fence` and live `collection_id` are **None**. The historical
selection remains on the enclosing `ArchivedAccount`. A fresh subscription is
required for current collection; an old receipt can never satisfy the adapter
checkpoint gate's requirement for a current source-bound fence.

## Verification and remaining work

New tests exercise actual native HMAC signing against fixed synthetic responses,
independently verify signatures and confirm secret/signature exclusion from archives.
Fresh subprocesses use `os._exit(23)` both mid-collection and after completion:
only the completed collection replays, and journal reopening never restores a
connected subscription. Tests also cover full-page pagination, multiple collection
selection, old hash-only logs, changed UID/permissions/baseline/cursors, response and
completion hash mismatch, stream interruption, malformed JSON, disk failure,
whole-record/torn-tail removal, CLI privacy and input immutability.

The independently retained response bodies reproduce the same synthetic
`AccountEvidence`, which passes exact native account/order/position comparison.
Passing that historical result into the adapter checkpoint gate is rejected because
it has no live fence. These are engineering fixtures, not real account qualification.

**31 new tests pass**. Full offline regression: **2,182 passed**, 12 PostgreSQL
integration tests deselected without a dedicated integration DSN. Ruff across
`apps tests notebooks`, CLI help, registry and whitespace checks pass.

```bash
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_account_archive.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
.venv/bin/python -m apps.ops.portfolio_account_archive_check --help
git diff --check
```

Actual environment, credential references, expected UID, independent baseline,
endpoint permission availability, account/price coverage, cash flows, UTC day-open
history and strategy policy remain required before execution bootstrap. This
increment closes the missing-REST-body evidence gap; it does not supply those
external inputs or qualify the remaining trading stages.
