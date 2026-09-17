# Installed gateway owns a fixed HTTPS request and its original receipts

Date: 2026-09-17. Local disposable TLS peers only; zero venue requests.

The [installed gateway](portfolio-egress-installed-gateway-2026-09-17.md) now has
an explicit TLS fixture mode. `gateway_tls.py` sends the one fixed unsigned
`GET /api/v3/exchangeInfo` through the gateway-owned marked socket, with durable
request accounting and raw-response evidence. It reuses the existing TLS source
selector, HTTP framing parser, journal writer and rate-field parser. The existing
joint account/market TLS collector is not yet connected to this gateway.

## Fixed request, installed trust and persistence

The installed fixture manifest is now `portfolio.installed_gateway_fixture.v2`,
with seven fixed source files including the TLS module. The base installer and
four-source installation bundle are unchanged. Historical v1 fixture manifests,
source copies and consumed scopes remain immutable. The ordinary-user namespace
harness explicitly selects TLS with `--tls-profile`; the default echo profile
continues to pass its five scenarios. Neither mode is a host deployment entrypoint.

The TLS mode reads one root-owned, held 0444 fixture trust file. Its SHA256 joins
the installed manifest, dedicated child identity, route and deny rules in the
borrowed binding. Only the trusted gateway owns the TCP/TLS socket; the child
receives no descriptor, destination, payload, request selector or credentials.
The logical authority is `rest.fixture.invalid:23456`, while the actual socket
connects directly to reserved `198.51.100.2:23456` in the isolated peer namespace.
There is no DNS lookup, proxy fallback, redirect, retry or reconnect. The shared
loopback-only TLS APIs retain their existing restrictions; none is widened to
accept real endpoints.

The existing attempt ledger and kernel lifecycle first persist the fixed operation
and acknowledge the five-second mark grant. Only then does the transport create
exclusive `tls.jsonl` under the same consumed scope and persist a connection
preparation selecting the exact pending-attempt and acknowledged-lifecycle prefixes.
The preparation precedes socket creation/connect. TLS uses hostname verification,
`CERT_REQUIRED` and TLS 1.2 or newer. Verified peer/certificate/cipher metadata is
persisted before the exact HTTP request bytes; request preparation is fsynced and
the binding rechecked before `sendall`.

Every decrypted chunk is timestamped immediately after `recv` returns, before
storage validation, hashing, fsync or parsing. Original chunk bytes are persisted
before interpretation. Header receipt is derived from the first retained chunk
that completes the header, and body completion from the chunk that completes the
bounded body. A delayed body or slow disk validation cannot refresh the header's
counter timestamp. These are local read-receipt clocks, not provider event times
or a qualified server-clock offset.

The fixed transport has a four-second deadline shared across connect, handshake,
send and reads, a 64 KiB header/body limit each, 4 KiB reads and a 2 MiB journal
with incident reserve. Synchronous disk operations are not preempted by socket
deadlines. Completion requires exact HTTP framing, status 200, valid original
rate fields, binding revalidation and local descriptor closure. Descriptor closure
does not claim a verified peer TLS close-notify exchange. Any failure attempts an
abort and outer kernel revocation; failures never refund or reopen the attempt.
The journal checks inode/mode/owner/link/prefix and exact bytes after append.
Failed fsync cannot leave an acknowledged completion on the tested filesystem.

## Classification, uncertainty and offline replay

The request bytes, method, path, logical host and literal destination are fixed.
The existing `exchange_info` preparation conservatively consumes one operation
and nominal weight 20 even if TLS fails before an HTTP request is sent. A separate
`prepared_tcp_connections` field counts the local connection preparation; it is
not a provider CONNECTIONS counter. The independent local peer confirms zero HTTP
requests for the wrong-certificate case, and exactly one for each other scenario.

`replay` validates canonical bytes, hash links, clock continuity, both companion
archives and their original prefix ordering. The selected attempt must still be
pending and the selected kernel prefix must end at `activated`. The exact request,
TLS verifier fields, original chunks, HTTP body/header hashes and rate fields must
agree before a complete transcript is reported. Incomplete or aborted prefixes
remain reviewable without a rate-evidence success report. Incomplete bodies have
no body-completion receipt. A hash-selected fabricated archive is not independent
source authentication, and historical replay never reconstructs installed authority.

The fixture response supplies REQUEST_WEIGHT count 20, plus RAW_REQUESTS and
CONNECTIONS limit definitions whose usage stays null. Provider connection charge,
current total usage upper bound and all-caller coverage remain unknown/unqualified.
All restart, real-source, network and trading admission flags stay false. The
nominal operation reservation, local TCP preparation, observed HTTP request and
provider quota counters are deliberately distinct evidence.

## Acceptance

**33 new / 557 focused Python tests pass. Six actual installed TLS scenarios and
all five updated echo regression scenarios pass.** Each TLS scenario runs 43
integration assertions (44 for the crash case), plus the reused base installation
checks. The additional installed source is included in dedicated-UID write/unlink/
chmod refusal tests. No host installation, network policy or service is changed.

| TLS scenario | Peer HTTP requests | TLS archive | Attempt after termination |
|---|---:|---|---|
| Normal | 1 | Complete | Succeeded, closed |
| Body delayed 1.2 seconds | 1 | Complete; original header receipt retained | Succeeded, closed |
| Wrong certificate hostname | 0 | Aborted before request preparation | Pending/uncertain |
| Duplicate weight counter | 1 | Original response retained, aborted | Pending/uncertain |
| Truncated body | 1 | Incomplete body, aborted | Pending/uncertain |
| SIGKILL after header chunk | 1 | Incomplete; no completion marker | Pending/uncertain |

Every managed case verifies revocation. The crashed controller leaves a kernel
permit until its original timeout; a marked diagnostic probe is denied afterward.
Fresh installed processes refuse the consumed scope and preserve all three exact
journals. The crash parent waits for the controller’s explicit post-fsync header
notification before SIGKILL; it does not manufacture a revoked record or flush the permit.

New tests cover all eight TLS event fsync failures, certificate failure, malformed
responses, in-fsync archive mutation and fully rehashed semantic changes. They also
verify that slow body delivery and deliberately slow archive validation preserve
the earlier header receipt. The focused regression includes installation, package,
collector, ledger, lifecycle, authority, TLS provenance and rate parsing suites.

Two fresh isolated system-Python replay processes reproduce all six sets of
attempt/lifecycle/TLS reports byte-for-byte and match the worker originals.
Selected originals, public fixture trust, source copies and replay driver are in
`data/egress-gateway-tls-2026-09-17-v3/`, pinned by the
[result JSON](portfolio-egress-gateway-tls-2026-09-17.json). Private fixture keys
existed only in disposable tmpfs and were not exported. Earlier diagnostic captures
remain unselected; the selected run uses immediate post-recv timestamps.
Ruff/format, evidence pins, document links and diff checks pass. The full application
suite and unrelated older standalone kernel scripts were not rerun.

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py --tls-profile --report data/NEW-GATEWAY-TLS.json
/usr/bin/python3 -I data/egress-gateway-tls-2026-09-17-v3/replay.py
```

Next integrate the bounded multi-operation local joint transport with explicit
request classification, per-operation budgets and durable gateway consumption;
account/market subscriptions, control frames and unknown connection charges still
need that integration. Actual source/all-caller policy, complete history and fresh
rate/clock qualification remain separate blockers. No new host window or bootstrap
retry is authorized. The frozen joint contract remains 17 GETs / 468 weight,
strict continuity 0/14 and trading blocked. Upstream sources and live order paths
are untouched; project status, reading index and infrastructure README are updated.
