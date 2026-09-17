# Installed gateway to native metadata receipt

Date: 2026-09-17. Phase: disposable local integration; no host rollout or real
venue access. This supersedes the stdlib-only consumer limitation in the
[installed receipt](portfolio-installed-tls-receipt-2026-09-17.md), while retaining
its exact original evidence and the [deadline/stall fixes](portfolio-installed-tls-receipt-stall-2026-09-17.md).
Machine-readable selection and verification pins are in the matching JSON.

## Result and boundary

One root-owned fixture HTTPS `GET /api/v3/exchangeInfo` now feeds an actual native
Nautilus consumer under dedicated UID/GID 20999. After the gateway revokes kernel
permission, the existing authenticated, credential-framed IPC carries original
response bytes and original header/body receive clocks. The child constructs
Nautilus 1.226.0 Rust `Currency` objects for BNB, BTC, ETH and USDT (precision 8),
then sends a final acknowledgement binding the native summary and entire payload.
A structurally valid precision-17 response completes TLS, but native construction
rejects it and the attempt remains pending without a final acknowledgement.

This is **native metadata consumption only**. It does not integrate the complete
ordinary-process 20-operation collector, signed account selectors, account mapping,
same-run routes, native signing or concurrent WS. The separate local joint budget
remains 16 GETs / 448 documented weight; the frozen real draft remains 17 GETs /
468 weight. This single-GET fixture does not consume or replace either contract.
`native_metadata_acknowledged` identifies this narrow receipt;
`native_collector_integrated`, network/trading admission and execution qualification
remain false. No freshness is regenerated from replay time.

## Runtime and custody

`gateway_native_runtime.py` builds a public CPython 3.12/Nautilus 1.226.0 capsule
as the ordinary project user. The wrapper retains it beside the selected report.
Only after entering disposable mount/network/PID namespaces does the root harness
copy regular, bounded, canonical members into a private root-owned tmpfs; paths,
symlinks, duplicates, oversized members and inventory mismatches are refused.
The capsule has 701 files / 213,365,841 bytes including its manifest. It contains
the interpreter/stdlib and imported Nautilus core files, without project credentials
or trading configuration. The mount becomes read-only, nosuid and nodev before use.

`NativeRuntime` hashes each file initially, keeps close-on-exec descriptors and
checks held/path identity, ownership, modes, size, timestamps and exact read-only
mount identity during use. These are repeated metadata/mount checks, not repeated
full content hashing. Root administration races, rollback, power loss and arbitrary
OS loader/library provenance are not qualified. The capsule is a selected fixture
runtime, not a portable deployment package or a new trust authority.

The unchanged base launcher drops capabilities and supplementary groups, sets
no-new-privileges, isolates child networking and authenticates exact PID/UID/GID.
The native runtime manifest pin joins its process binding. Native source executes
in a separate child namespace of Python globals, preserving the old receipt parser
profile. Native import rejects root before loading the package. Root uses only
stdlib to calculate the expected summary; actual object construction occurs in
the child. Supplemental fixture manifest v5 pins eleven project-owned sources;
the base installer/launcher bytes remain unchanged.

The native journal has an explicit separate profile and requires an explicit
native parser during replay. Rehashed currency/version/clock changes, profile
downgrades and missing parser selection are rejected. Prior receipt, TLS, IPC and
echo profiles retain their schemas and meaning. Runtime remount drift, child
SIGSTOP and gateway SIGKILL cannot create a final receipt or reopen the scope.

## Verification and retained evidence

- **865 focused Python tests pass**, including 25 new native/runtime tests,
  in 166.17 seconds. Three existing fork-after-native-thread deprecation warnings
  remain. The initial broad run exposed a test's assumption that a same-size write
  changes timestamps within one clock tick (864 passed / one failed). That test now
  explicitly changes size to verify the metadata contract; the full rerun passes.
- **35 actual current-source disposable scenarios pass**: seven native, eleven
  stdlib receipt, six TLS, six IPC and five echo. Each scenario also runs the base
  40-check installation acceptance. Source permissions, actual kernel isolation,
  fixed-scope restart refusal and unchanged host observations are verified.
- Native scenarios: success, slow body, precision rejection, runtime rw-remount
  drift, bad certificate, stopped consumer timeout/kill/reap, controller crash.
  Native checks per scenario are 58, 58, 58, 60, 57, 61 and 60 respectively.
- Two fresh system-Python replays, with socket creation/DNS blocked, reproduce all
  35 selected original attempt/kernel/TLS/receipt report sets byte-for-byte.
- Two fresh ordinary-user replays using the retained capsule recreate actual native
  objects from original TLS bytes and reproduce the precision-17 exception. All
  capsule files are rehashed before native import. Source/native module pins match.
  The three drift/stall/crash payloads can map offline, but their original missing
  acknowledgements stay false. Bad-certificate evidence has no completed receipt.
- Ruff, formatting and diff checks pass. No upstream files, live execution path,
  host service, host firewall or real venue scope were changed.

Selected local artifacts are under `data/installed-native-receipt-2026-09-17/`:
exclusive report/archive/source copies, `selection.json`, frozen runtime tarball,
`replay.py`, `extract-runtime.py`, `native-replay.py`, and two outputs per replay.
They are ignored local data; the tracked JSON pins them rather than committing
third-party runtime binaries. The initial six-scenario diagnostic report is not
selected. Previous evidence directories remain unchanged.

To replay the retained selection (no capture, credentials or root):

```bash
/usr/bin/python3 -I data/installed-native-receipt-2026-09-17/replay.py
data/installed-native-receipt-2026-09-17/offline-runtime/bin/python3.12 -I data/installed-native-receipt-2026-09-17/native-replay.py
```

## Next implementation entrypoint

Extend this boundary to the existing full native joint collector, with fixed root
validation for signed selectors/routes, durable per-operation accounting and
original receive clocks for concurrent TLS/WS. Keep native dependencies confined
to the isolated consumer. Then qualify actual authority/complete shared-egress
coverage, provider charges, rate/clock use and any separately authorized host rollout.
No consumed bootstrap, public-depth or ADR-017 scope may be reopened. Equity,
UTC baseline and live trading qualification remain blocked independently.
