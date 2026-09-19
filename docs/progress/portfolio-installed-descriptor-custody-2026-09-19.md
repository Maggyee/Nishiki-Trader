# Installed descriptor custody and transport resource prerequisite

Date: 2026-09-19. Phase: disposable local acceptance only.
Base commit: `5de77444457c3748fce7c0ba2cecb67850143d84`.
Machine-readable evidence: [pinned report](portfolio-installed-descriptor-custody-2026-09-19.json).

The six-read controller previously reached 1,009 sampled descriptors under its
unchanged 1,024 limit, leaving only 15 for further transport integration.
`TrustedInstallation` repeatedly opened the same ancestor directories for protected
sources and original files. It now caches borrowed descriptors by canonical absolute
path, including the root, shared ancestors and already held files. In current-source
six-read acceptance, the maximum sampled count is **844**, a reduction of **165**,
leaving **180** spare without changing limits or discarding held originals.

## Custody semantics

The installation owns each cached descriptor until close; callers borrow handles
and must not close them. New files still require no-follow opens, a root-owned
single-link regular file, the requested mode and bounded exact bytes. Existing
paths retain their original parent-relative identity. Reborrowing a file with a
different mode is refused. Relative paths, dot/parent aliases, redundant separators,
double leading slashes and trailing slashes are refused (the root `/` is valid).

Borrows recheck held inode/path metadata and bytes, the mount namespace and the
selected account. Directory acquisition verifies before and after traversal; new
files verify again after acquisition. During construction the account check starts
once the account is selected. Observed drift or a failed acquisition closes all
owned handles and permanently invalidates the installation. Restoring changed bytes
or mode does not reopen authority. Foreign processes can neither borrow handles nor
close the original owner's descriptors. This remains a single-owner process contract;
no thread-safety or continuous race prevention is claimed.

The base installation remains schema v2 with four fixed sources. The supplemental
fixture remains manifest v10 with sixteen sources. The revised verifier changes the
base archive hash, so `installation_selftest.py` now pins
`9240714aaf4977a44633d744d51775e0c3a786051c98c02b131d4ddf08004142`.
The installer and helper-entry bytes are unchanged. This selects a new **disposable
acceptance** bundle; the host installation has not been updated or deployed.

## Verification

**912 tests pass** in 57.49 seconds without warnings, including **24 new cases**;
**29 actual disposable scenarios pass**. Two original replays cover all 29 scenario
sets, and two frozen-native replays cover 24 sets and reproduce **55 request
envelopes**. Each replay pair is byte-identical. Exact hashes are in the linked JSON.
The new unit cases cover repeated borrows without growth, 32 sibling files requiring only
32 new descriptors, cached byte/inode/ancestor/mode/account/namespace drift,
canonical-path refusal, mode conflicts, failed acquisition cleanup and foreign-owner
refusal. The existing gateway, installation and package regression batch is retained.

Actual acceptance uses private mount/network/PID namespaces and local fixture peers:
ten six-read route scenarios, seven signed-account cases, seven native metadata
receipt cases and five echo/kernel lifecycle cases. The six-read cases include
success, two-hop routes, missing/insufficient books, precision/duplicate/disabled
symbols, stopped child, controller crash and code drift. These current-source
scenarios supplement the previous 63-scenario historical route acceptance.

At the existing `activated` and `receipt_prepared` sampling points, sequence
acceptance now requires at least **64 spare descriptors** under 1,024 (at most 960
observed). The 844 maximum satisfies this floor. This is sampled headroom, not a
continuous peak measurement, an OS reservation or acceptance of concurrent sockets.
The frozen child runtime still contains 701 pinned files / 213,365,841 bytes and
NautilusTrader 1.226.0; root does not import native modules.

Exact reports, originals, sixteen supplemental sources, four base sources, installer,
base/gateway harnesses and the canonical base bundle are retained under
`data/installed-descriptor-custody-2026-09-19/`. Original replays check all these pins;
the base bundle's members must equal the retained source/installer bytes. Two fresh
ordinary-user original replays and two frozen-runtime native replays compare exact
output bytes, preserving original clocks and missing acknowledgements. Native
reconstruction does not grant a previously absent parent acknowledgement.

The earlier route report's 27 artifact pins, 63 scenario originals and sixteen source
copies remain unchanged. The empty `routes-final.json` is an unselected diagnostic:
the first launch stopped at `bundle_size_or_sha256` while the disposable harness
still pinned the old base archive, before any namespace/network/native execution.
After updating that pin, `routes-accepted.json` is the selected route report.
Ignored raw evidence and runtime files are not committed.

## Boundary and next entrypoint

This completes the descriptor resource prerequisite. Concurrent gateway-owned
TLS/WS consuming the original-derived symbol union is **still pending**. Keep
original clocks, per-operation consumption, protected originals and inherited
resource limits when adding it. Sampling alone proves neither complete caller
coverage nor capacity for the future transport workload.

No upstream source, live order path, real venue request, host installation,
credential, firewall maintenance or service changed. Host before/after observations
match. Consumed bootstrap, depth and ADR-017 scopes remain closed. Stream fences,
atomic account snapshots, quote event-time freshness, source authority, provider
quota and full-account/UTC equity remain unqualified; real network/trading admission
remains blocked. `docs/project-status.md`, the reading list and infrastructure README
are updated with this prerequisite and the unchanged next integration step.
