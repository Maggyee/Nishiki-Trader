# Installed native signed-request custody

Date: 2026-09-17. Phase: disposable local request validation and accounting.
This follows [native metadata receipts](portfolio-installed-native-receipt-2026-09-17.md)
and [fixed-token IPC custody](portfolio-installed-joint-ipc-2026-09-17.md).
The matching JSON pins exact source, report, archive selection and replay bytes.

## Result

The installed isolated consumer now generates complete request envelopes for a
fixed 20-step rehearsal, including eight signed REST reads and one signed WS
subscription. It uses Nautilus 1.226.0's native `ed25519_signature` under dedicated
UID/GID 20999, without capabilities, privileged descriptors or an IP transport path.
Root issues a fresh challenge for each step, verifies exact selectors and original
clock bounds, verifies Ed25519 using system OpenSSL, and persists the request hash
before returning a credential-authenticated receipt. Root never imports Nautilus.

A separate `portfolio.fixture_native_requests_ledger.v1` profile and fixed
`fixture-native-requests-v1` scope keep request custody distinct from prior token
receipts and transport outcomes. `requests.jsonl` binds each original request to a
pending ledger prefix. The final child receipt binds the exact request hash;
only then does the ledger record a successful **custody** outcome. No network
permission, socket dispatch, venue acceptance or consumed-scope restart follows.
The old ledger profiles and original selected evidence retain their meaning.

## Selected requests and limits

The frozen order matches the local pilot's 20 operation classes: initial clock,
account connect/subscribe, four before-account reads, metadata/books, market connect,
three depth selectors, linked clock, four after-account reads, final clock and
unsubscribe. Root independently fixes the order and checks the 16 GET / 448 documented
weight / two connection classifications. Market connection charge remains unknown;
448 is a synthetic documented reservation, not observed provider usage. The real
17-GET / 468-weight draft stays unchanged and unactivated.

The signed REST selectors are account-wide `/api/v3/account` and `/api/v3/openOrders`,
with only timestamp and recvWindow parameters and the exact fixture API key header.
All REST methods are GET. The WS subscription uses canonical parameter signing.
Depth symbols are fixed BTCUSDT, ETHUSDT and BNBUSDT, limit 100; market streams match
those symbols. Unsubscribe uses explicitly synthetic subscription ID zero.
Neither routes nor the subscription ID are derived from same-run account/venue
responses. This emitter is not the full native joint collector.

The Ed25519 seed/public key are the **public RFC 8032 test vector**. They are not
operator credentials and cannot authenticate a real source or venue. There is no
credential discovery, path argument, arbitrary endpoint or caller-supplied weight.
Source/runtime custody and the exact child process binding provide the local
fixture boundary; a known test signature alone provides no caller authority.
OpenSSL reads bounded public-key/message/signature bytes through anonymous file
descriptors with a fixed environment and timeout. No crypto algorithm is reimplemented.
The system OpenSSL/loader libraries remain part of the fixture's system trust;
this work does not qualify them for a real deployment.

Each challenge binds index, random nonce and original wall/monotonic clocks. Request
receipts must fall within five seconds and 50 ms clock consistency. The envelope
binds the complete challenge hash, preventing a response from satisfying another
challenge. Exact canonical shapes reject extra headers/parameters, POST/order
paths, signature substitution, unsigned private reads and alternate encodings.
The native consumer and protected root sources use the existing frozen runtime
manifest and unchanged base launcher. Supplemental manifest v6 pins twelve sources.

## Failure and replay behavior

The root-owned ledger is prepared only after validation; success receipts require
both ledger and request journal persistence. Failures keep consumed attempts and
block reuse. The actual midpoint barrier has ten prepared requests and nine
acknowledged requests. Child SIGKILL, code/account/storage changes, controller
SIGKILL and runtime rw-remount drift all preserve that distinction; fresh installed
processes cannot reopen the consumed scope. Even a marked root fixture socket is
kernel-denied because this profile never grants egress.

Detached replay verifies selected bytes, canonical chains, every exact request,
nine signatures in a completed session, original receive times and active pending
ledger prefixes. Received requests must precede ledger preparation, and request
acknowledgements must precede successful ledger outcomes and terminal records.
Previous outcomes must precede the next challenge. Missing acknowledgements and
missing final outcomes remain incomplete; offline reconstruction never fills them
in. A ledger preparation without its corresponding original request record is
rejected as unbound evidence, not reported as a successful custody event.

## Verification

- **52 new / 733 focused tests pass**, no warnings, in 46.81 seconds. Coverage
  includes every native selector, signature/selector/challenge/clock mutation,
  malformed shapes, fixed budget changes, durable receipt ordering, rehashed replay
  tampering, incomplete outcomes and the existing installation/ledger/TLS regressions.
- **42 actual current-source disposable scenarios pass**: seven native requests,
  seven native metadata, eleven stdlib receipt, six TLS, six IPC and five echo.
  The seven request scenarios have 63, 63, 63, 63, 63, 64 and 64 checks, plus each
  scenario's original 40-check base installation acceptance.
- **Two independent system-Python replays** reproduce all 42 original report sets
  exactly, with socket construction and DNS disabled. Root-free OpenSSL verification
  independently checks signatures using the selected public key.
- **Two independent frozen-runtime native replays** regenerate all **80** selected
  request envelopes byte-for-byte across seven success/failure cases, covering **39**
  retained signatures. The original 20/20 success and 10/9 failure preparation/
  acknowledgement counts remain unchanged. Seven native metadata regression sets
  also reproduce actual Currency construction and precision-17 refusal.
- Ruff/formatting, source/artifact hashes, documentation links and diff checks pass.
  Host account/install observations remain unchanged; venue requests are zero.

The first broad run with final production sources exposed a test-fixture mismatch:
its reused IPC socket waited only 0.2 seconds while the test replayed each growing
journal before acknowledgement (732 passed / one timeout failure). The fixture
now matches the production consumer's five-second wait; the full 733-test rerun
passes. No production timeout was relaxed. Earlier development runs and the initial
seven-scenario diagnostic report are not the selected final evidence.

Retained originals live under `data/installed-native-requests-2026-09-17/` with a
README, six final reports, exact protected source copies, per-scenario archives,
`selection.json`, public frozen-runtime bundles and replay drivers/outputs. They
are ignored local data. The tracked JSON contains their pins; no third-party runtime
binaries, live keys, local databases or upstream checkouts are committed.

Replay without root, credentials or new capture:

```bash
/usr/bin/python3 -I data/installed-native-requests-2026-09-17/replay.py
data/installed-native-requests-2026-09-17/offline-runtime/bin/python3.12 -I -B data/installed-native-requests-2026-09-17/native-replay.py
```

## Next implementation entrypoint

Connect validated requests to gateway-owned TLS/WS and the existing full native
collector, deriving routes and subscription selectors from original same-run
responses. Keep per-operation preparation, original receive clocks, expiring
permissions and conservative failure handling across that boundary. Native metadata
response consumption and signed-request custody currently remain separate profiles.
Actual authority, complete shared-egress coverage, provider charges, fresh rates/
clocks, host rollout, qualified account/equity baselines and trading remain blocked.
No consumed bootstrap, public-depth or ADR-017 scope may be reopened. Upstream
source and the live order path were not touched; no new ADR or service is required.
