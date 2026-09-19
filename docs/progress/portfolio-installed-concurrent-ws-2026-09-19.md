# Installed concurrent TLS/WebSocket upgrade and control acceptance

Date: 2026-09-19. Phase: disposable local acceptance only.
Base commit: `e83ffc5` (full hash in the [pinned report](portfolio-installed-concurrent-ws-2026-09-19.json)).

The installed controller now follows its six-read native route sequence with two
concurrent gateway-owned TLS/WebSocket channels. The account channel targets the
fixed fixture `/ws-api/v3`; the market channel's combined-stream path uses only the
symbol union rederived from the same-run metadata/account/book originals. This
milestone covers Upgrade, ping/pong and close handshakes. **Signed account
subscription, private/market event delivery to native consumers and the full joint
REST/depth collector are still pending.**

## Implementation and custody

`gateway_concurrent_ws.py` adds the nested `concurrent-ws-v1` scope beneath the
consumed route parent. It replays all six original bundles before selecting symbols;
a saved route report alone is insufficient. It pins the route archive, bundle set,
route result, base/supplemental manifests, CA and structural network environment.
Transport must start within five seconds of the original route completion, with
consistent UTC/monotonic deltas. This is a local fixture timing rule, not provider
quote freshness or a new account observation.

The controller persists both fixed connection preparations before recording the
kernel activation intent. Two fixed `198.51.100.2:23456` marked sockets then share
one nonrenewable five-second kernel permit. The four-second total I/O deadline is
measured from the pre-grant journal clock, so verification and parent barriers spend
that allowance. There is no caller-selected address, DNS lookup, socket handoff,
retry, grant renewal, real hostname or credential input.

One event loop owns both sockets and serializes journal mutation; it does not make
the installation verifier thread-safe. Before each wire operation the controller
rechecks held installation/original bytes and network structure. TLS validates the
pinned CA and role hostname. Exact Upgrade requests, verification records and
received chunks are durably stored; receipt clocks are sampled immediately after
read, before custody checks. Header/control interpretation uses those originals.
Both channels must reach their fixture ping/pong exchange before either prepares
close. Masked pong and close frames are persisted before sending. Text/private
payloads, early close and unexpected control sequences are refused in this profile.

On any failure the controller cancels the sibling task, closes owned sockets and
attempts kernel revocation even if journal persistence or socket close fails.
Successful completion requires both original peer closes, socket closure and a
recorded revocation. Source drift or failed journal validation permanently disables
further journal appends; the surviving prefix may therefore retain an uncertain
revocation despite actual cleanup. A replay never fills that gap from a later
process observation. SIGKILL relies on kernel expiry and leaves an incomplete,
nonresumable original. A fresh installed process refuses the consumed route parent
without changing any originals.

Supplemental manifest **v11 pins eighteen sources**, adding the concurrent module
and shared frame parser. The base v2 installation bundle is unchanged. To allow
root's stdlib-only Python to load framing without importing Nautilus, `DepthError`
and `MAX_FRAME` now live in `portfolio_ws_frames.py`; the depth mapper imports the
same shared definitions. Frame behavior stays covered by existing regression.
Explicit integer byte order and compatible asyncio interfaces support the system
Python 3.10 as well as the project's Python 3.12. Root still never imports native
packages; six-read native construction remains in the isolated dedicated UID.

## Verification and retained evidence

**1,151 tests pass** in 169.13 seconds with no warnings across 28 test files,
including **32 new cases**. **30 current-source disposable scenarios pass**. The
linked JSON records exact source/artifact pins, per-scenario transport states,
resource samples and replay counts.
The 32 new tests cover original-route selection, complete and truncated transcripts,
fully rehashed changes to target/nonce/certificate/Upgrade/control/clock/closure,
permanent storage invalidation, owner/closed-handle refusal, sibling cancellation
and revocation after persistence or socket-close failure. A fresh system-Python
process loads the frame parser and checks close/extended-length framing without
project or native imports. Existing native depth, ordinary-process TLS/joint
transport and installed gateway paths are included in regression.

**Eight actual concurrent scenarios pass**, exercising direct routes, two-hop routes, bad
certificates, bad Upgrade responses, early peer close, stalled peers, source drift
and controller SIGKILL. Every case first performs the actual six native reads.
The peer waits until both Upgrade requests exist before responding, then waits
for both upgrades before pinging: successful control exchanges require actual
simultaneous sockets. Regressions also run the ten six-read route, seven signed
account and five echo/kernel scenarios with the final sources. Terminal permission
is checked directly and a marked socket is denied after completion/failure/expiry.

Descriptor samples include the existing activation/pre-receipt points plus WS
activation and both-live barriers. The current maximum sampled controller count is **848**, leaving **176** under
1,024; the successful two-channel stage itself samples 106/108 descriptors. The
acceptance floor remains at least 64 spare, with no descriptor limit changes. Counts are sampled, not continuous peaks
or a reservation for future native consumers. The child runtime remains the same
701-file frozen CPython/Nautilus capsule; closing the native read consumers before
WS materially reduces descriptors during this particular stage.

Exact original archives, reports, eighteen protected source copies, base sources,
installer and harnesses live under ignored
`data/installed-concurrent-ws-2026-09-19/`. Detached original replay rederives routes
before checking WS originals, and frozen-native replay reconstructs the original
six-read requests and native mappings without creating a missing WS/native receipt.
Two fresh runs of each replay produce byte-identical outputs: original replay
covers all **30 scenario sets** and **eight WS archives**; frozen-native replay
covers **25 scenario sets** and reconstructs **95 request envelopes**. Prior descriptor evidence (46 retained artifact pins, 29 scenario sets and sixteen
source copies) and route evidence (27 artifact pins, 63 scenario sets and sixteen
source copies) both verify unchanged.

Three preliminary, unselected runs exposed Python 3.10 incompatibilities:
`asyncio.timeout_at`, `ssl_shutdown_timeout`, and implicit `int.from_bytes` byte order.
The first two stopped before successful WS exchange; the third reached control
processing. Their empty report files and runtime capsules remain diagnostic only.
The one-scenario `success-verified` smoke run passed. A preliminary full batch then
exposed Python 3.10’s distinct asyncio timeout exception after Ruff automatically
rewrote the catch; `ws-accepted.json` remains an empty unselected diagnostic. The
compatible catch is now explicitly preserved and directly tested under system
Python. Final selection uses the full eight-scenario `ws-final` and regression reports. These are all local
fixture runs and do not consume or reopen any real venue scope.

## Next entrypoint and boundaries

Next join native signed account subscription to the already owned account socket,
validate the exact selector/signature through the existing dedicated-UID boundary,
and deliver original responses/events for native acknowledgement. Preserve
per-operation consumption, original timestamps, shared cancellation/expiry and
bounded buffers. Then integrate the remaining concurrent REST/depth operations and
account fences; the accepted ordinary-process 20-operation collector is not yet
connected wholesale to this installed gateway.

The account connection has documented weight 2; market connection charge and actual
shared usage upper bounds stay unknown. A TCP/TLS/Upgrade success supplies no
provider authentication, complete caller coverage, event-time freshness, account
stream fence, atomic snapshot, full equity or UTC baseline. All real network and
trading admission flags remain false.

No upstream checkout, live order path, host installation, service or credential was
changed. No real venue request or host firewall maintenance occurred. Host
before/after observations match. Consumed bootstrap, depth and ADR-017 scopes stay
closed. Project status, reading list and infrastructure README point to this
upgrade/control milestone and the pending signed/native integration.
