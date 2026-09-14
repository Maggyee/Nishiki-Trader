# Local TLS and Upgrade provenance acceptance — 2026-09-14

The project now captures actual TLS verification and original HTTP/WS Upgrade
response bytes from ephemeral local peers, without changing upstream or adding
dependencies. A separate offline CLI replays selected private archives in fresh
processes. This completes the source-recording primitive's local acceptance;
the full joint transport and real shared-egress admission are still outstanding.

The profile is `portfolio.loopback_tls_provenance.v1`. It is separate from the
synthetic joint journal, native loopback joint collector, and proposed real
`portfolio.testnet_joint_observation.v1` profile. The
[real capture draft](portfolio-testnet-joint-capture-contract-2026-09-14.md) and its
JSON remain unchanged: no actual capture or first-request budget exception is
enabled. The completed public v1/v2 probes and ADR-017 session remain consumed.

## Captured evidence

`apps/strategies_nautilus/portfolio_tls_provenance.py` uses standard-library
asyncio/OpenSSL TLS. The caller explicitly selects an ephemeral PEM trust root
and its SHA256, a new private archive, and one of three fixed fixture authorities:

| Role | Logical URL | Actual network destination |
|---|---|---|
| REST | `https://rest.fixture.invalid:PORT/api/v3/exchangeInfo` | Literal `127.0.0.1:PORT` |
| Account Upgrade | `wss://account.fixture.invalid:PORT/ws-api/v3` | Literal `127.0.0.1:PORT` |
| Market Upgrade | `wss://market.fixture.invalid:PORT/stream?streams=btcusdt@depth@100ms` | Literal `127.0.0.1:PORT` |

Input checks run before archive creation and socket creation. Missing/changed
trust, nonfixture authorities, real testnet/production URLs, alternate paths,
query additions, credentials in URLs, fragments and plaintext HTTP fail there.
Reserved fixture names are used for certificate hostname verification; the network
connect uses the literal local address. Proxy environment variables and DNS
fallback are not consulted. Existing archives and symlinks cannot be overwritten.

An exclusive mode-0600 archive and its directory entry are persisted first.
The connection preparation is fsynced before the TLS connect. The TLS receipt is
fsynced before the sole GET/Upgrade preparation, which is also fsynced before send.
The receipt records selected authority/port/path, actual peer address, actual peer
certificate SHA256, TLS version/cipher, `CERT_REQUIRED`, hostname verification and
the selected trust-root digest. A successful TLS handshake verifies the local
fixture certificate using OpenSSL; recorded flags supplied by a caller cannot
disable verification or replace the peer certificate.

Each returned decrypted chunk is retained before HTTP framing or status parsing.
Original header bytes therefore preserve casing, ordering, duplicates and spacing;
the parsed ordered header pairs are a separate result. Partial headers/bodies,
bad Upgrade responses and redirects remain in failed archives. Selected byte
hashes and lengths bind header/body interpretation to earlier chunk receipts.
Every row includes UTC/monotonic receipt clocks and a previous-row digest.

REST acceptance requires HTTP/1.1 200 and one bounded Content-Length; compressed,
chunked, duplicate-length and coalesced trailing-body responses fail. Other duplicate
headers remain original evidence: the existing rate parser independently refuses
duplicate weight counters. WS acceptance checks HTTP/1.1 101, Upgrade/Connection,
and the RFC 6455 nonce/accept relation. Unrequested extensions/subprotocols,
duplicate critical headers and invalid accept values fail.

The WS primitive ends after Upgrade and TLS closure. It sends no authentication,
subscription or WebSocket data/control frame and does not run a WebSocket frame
engine. Bytes coalesced after the Upgrade header are retained and explicitly
counted as unprocessed tail bytes. Later buffered/arriving frames are not claimed
as captured. This is handshake acceptance, not a native WS replacement or joint
account/market collection. No strategy, account map or quote is constructed.

## Bounds and failure handling

Each invocation has one connection and one GET/Upgrade, with at most 10 seconds
of asynchronous capture and one shared five-second close allowance. The actual
TLS stream shutdown timeout is one second within that close allowance. There is
no redirect, retry, reconnect, endpoint fallback or archive reuse after failure.
Header bytes are limited to 64 KiB, REST body to 16 MiB, decrypted read chunks to
4 KiB, and serialized archive to 24 MiB. A rejected final chunk is retained before
its size/framing refusal when the archive still has capacity.

Cancellation, invalid certificates, incomplete replies, timeout and close failure
retain an abort without a completion marker. A persistence failure permanently
disables further journal appends and attempts to truncate the unacknowledged row,
including a completion row whose fsync failed. Tests cover every fsync through
completion; none can replay as complete on the tested filesystem. Synchronous
filesystem calls cannot be preempted by the async timeout. If storage also rejects
truncation, the file is ambiguous: a failed capture must never be selected for
successful replay, even if bytes happen to remain readable. No automatic report
is published after capture raises.

## Detached replay

The read-only entrypoint requires the original archive SHA256 and a distinct new
private output. It has no capture, credential or endpoint options:

```bash
.venv/bin/python -m apps.ops.portfolio_tls_provenance \
  --archive data/SELECTED-LOCAL-TLS.jsonl \
  --archive-sha256 SELECTED-ORIGINAL-SHA256 \
  --report data/NEW-LOCAL-TLS-REPLAY.json
```

Replay checks private-file ownership/mode, original hash, canonical row chain,
clock ordering, completed receipt order, fixture endpoint/peer/trust binding,
recorded verifier settings, raw-byte availability before interpretation and the
HTTP/Upgrade semantics. The output retains original metadata, original body hash
and unprocessed Upgrade-tail count. Two fresh CLI processes produce identical
reports and leave the archive unchanged.

Replay does not repeat TLS authentication or prove the origin of a manually
fabricated archive. Local TLS trust does not identify a NAT egress address or all
other callers. `actual_exchange_source_verified`, `shared_egress_verified` and
`network_admitted` remain false in every report.

## Verification and next work

**53 new tests pass** using actual local TLS servers with ephemeral OpenSSL
certificates. They cover all three roles, untrusted and wrong-host certificates,
raw/duplicate headers, partial/oversized responses, nonce failures, coalesced
unprocessed frame bytes, cancellation/timeouts, close failure, all ten fsync
positions, zero-network source refusals, archive reuse, replay tampering and two
independent CLI processes. Test networking permits only literal 127.0.0.1; no
exchange endpoint, real key, external provider or existing private session file
was accessed. Full offline regression: **3,015 passed, 12 deselected in 280.71
seconds** (`-m 'not network and not postgres'`). The Postgres integration cases
have no dedicated test DSN. Ruff for apps/tests/notebooks, changed-file formatting,
research registry and diff checks pass; project status records these results.

Next integrate an appropriate provenance-capable transport with the joint journal
and its full frame/control/lifecycle behavior. The installed native WS interface
still lacks the required accessors; this local primitive does not change that
interface. Also implement actual admission from authenticated pre-existing rate
samples and complete bound-egress records. A real handshake is post-connect
evidence; pre-connect checks must establish prior sample provenance, limits,
egress coverage and the transport's recording capability. Missing seed/egress
evidence still blocks the first external request under the draft. No such records
or trusted gateway authority are invented here.

All account/valuation/baseline/runtime/order qualifications remain unchanged and
false for this work; equity and loss inputs stay null and strict continuity stays
0/14. No upstream, live order path, schedule, dependency, risk policy or consumed
scope was changed. `docs/project-status.md` and the agent reading list are updated.

Changed files: the strategy and ops `portfolio_tls_provenance.py` modules,
`tests/strategies_nautilus/test_portfolio_tls_provenance.py`, both app READMEs,
`docs/agent-reading-list.md`, `docs/project-status.md`, and this report.
