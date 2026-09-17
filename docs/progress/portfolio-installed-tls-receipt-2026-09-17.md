# Installed HTTPS response delivery to the isolated dedicated UID

Date: 2026-09-17. Disposable installation and local TLS only; zero venue requests.

The installed gateway now carries an actual fixed HTTPS response back to its
isolated dedicated-UID consumer. The consumer requests `exchange_info`, root
persists the attempt before granting its five-second kernel permission, and root
owns the marked TLS socket. After retaining and validating the complete response,
root closes TLS and revokes kernel permission **before** transferring response
bytes. An authenticated final digest acknowledgement precedes the ledger outcome.

This closes the single-request response-data gap between installed transport and
IPC. It does **not** connect the full native joint collector. The child is a fixed
stdlib consumer which validates the HTTP body and rate fields using held parser
sources. Signed account selectors, same-run routes, multi-operation transport,
concurrent WebSockets and native account/quote mapping remain pending. The earlier
20-token IPC mode still grants no kernel permission and claims no wire outcome.

## Implementation and failure boundaries

`gateway_tls_receipt.py` reuses the unchanged pinned launcher and `ControlChannel`:
SOCK_SEQPACKET, per-message kernel PID/UID/GID credentials, canonical envelopes,
1,024-byte packet bounds and refusal/closure of transferred descriptors. The new
data allowlist accepts canonical base64 chunks of at most 512 bytes. There is no
caller-selected endpoint, method, body, credential, source code or socket handoff.
The fixed request remains the unsigned local exchangeInfo GET to reserved peer
198.51.100.2:23456 with verified TLS for rest.fixture.invalid.

The payload contains exact original HTTP headers/body, the selected TLS archive
hash and original root header/body receipt timestamps. It is limited to 180,000
bytes; the existing 64 KiB header/body bounds remain. Stop-and-wait transfer has
bounded packet count and a five-second total deadline on each side; individual
packets cannot renew that deadline. The consumer validates framing, lengths,
clock ordering and rate fields before acknowledging the complete payload hash.
Receiving it later never refreshes the original rate-counter timestamp.
Synchronous filesystem/identity operations are not preempted by these deadlines.

Root retains an exclusive `receipt.jsonl`, preparing and fsyncing the payload hash
before sending data. Its records bind the original pending-attempt and already
revoked kernel prefixes, selected TLS bytes and runtime binding. Installation,
child identity, storage bytes/mode and deadline checks surround transfer and
persistence. A missing/wrong acknowledgement, failed fsync or observed drift leaves
the attempt consumed and pending. Complete wire evidence remains distinguishable
from incomplete delivery evidence; no resend or scope reopen follows.

The offline reviewer replays all original companions, reconstructs the exact
payload from raw TLS chunks and verifies preparation/revocation/acknowledgement/
outcome ordering. Callers cannot substitute a precomputed TLS report or payload.
An acknowledged receipt with no ledger outcome remains explicitly distinguishable
through `attempt_outcome_recorded`. Reports never reconstruct live source authority
or current kernel state. Fsync/crash tests do not qualify power loss or rollback.

The supplemental manifest is **v4 / nine protected sources**. The base installer,
launcher, one-GET ledger scope and previous IPC-only profile are unchanged. There
is no host installation or service. Historical evidence and real consumed scopes
remain intact; all project/site packages remain outside the root import path.

## Verification and retained evidence

The [machine-readable report](portfolio-installed-tls-receipt-2026-09-17.json)
pins final source bytes, exact tests, originals and replay outputs.

**38 new / 828 focused tests pass** (170.11 seconds), with three existing
fork-after-native-thread DeprecationWarnings. Ruff, formatting and diff checks
pass. The new tests cover actual credential-framed response transfer, header-age
preservation, fsync/mutation/channel failure, forged final acknowledgement,
revocation-before-delivery, rehashed companion substitutions, clock jumps, malformed
payloads, descriptor leaks, wrong credentials/sequences and total deadlines.

Ten actual installed response scenarios pass: success, slow body, bad certificate,
duplicate rate header, truncated body, controller SIGKILL after headers, and four
post-TLS/pre-delivery faults (child SIGKILL, controller SIGKILL, installed source
drift, storage drift). The first two finish with acknowledged delivery and a closed
attempt. The four post-TLS faults preserve complete TLS but only a prepared receipt
and pending attempt; kernel permission was already revoked. Controller death also
causes the isolated orphan to exit, after which the namespace parent reaps it.
The early controller death still exercises the original kernel TTL expiry.

All six old TLS, six IPC-only and five echo scenarios also pass under manifest v4.
Each scenario checks the actual dedicated UID, kernel/file access refusals,
protected inventory, consumed-state sentinel and fresh-process no-reopen behavior.
Selected host observations and caller namespaces match before/after.

Two fresh isolated system-Python replays reproduce all **27** original scenario
sets using retained exact sources, with socket creation and DNS disabled.
Retained originals are under `data/installed-tls-receipt-2026-09-17/`; the earlier
`data/installed-tls-receipt-initial-2026-09-17.json` is diagnostic and unselected.
No fixture private key is exported. Full unrelated application tests were not run.

Next integrate the full native collector's signed REST/WS requests, validate exact
read selectors and routes in the root boundary, and retain root receive clocks
through concurrent data/control traffic and per-operation durable consumption.
The ordinary local fixture remains 16 GETs / 448 documented weight; the frozen
real draft remains 17 GETs / 468. Unknown provider charges, actual all-caller
coverage, clock/source authority, qualified equity and trading stay blocked.
No upstream source, live runner, SignalEvent, SourcePolicy or schedule changed.
