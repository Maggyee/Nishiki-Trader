# Bounded shared-egress maintenance window

The existing-IPv4 design now has an isolated implementation of a **12-second
collector permission and 20-second competing-traffic blackout**. This is an
alternative to the incomplete destination list demonstrated by the
[shared-source acceptance](portfolio-shared-egress-acceptance-2026-09-16.md).
It has not been deployed, and the operator has not accepted a service interruption.
The [machine-readable proposal](portfolio-maintenance-window-2026-09-16.json)
keeps deployment and network admission false.

## Failure behavior implemented and exercised

The new `FixtureMaintenanceWindow` uses two nftables timeout sets. One atomic
transaction adds the fixture WAN interface to the blackout set for 20 seconds and
the collector destination to the permit set for 12 seconds. Activation and terminal
revocation are serialized under a process-owned lock. A failed/uncertain activation
consumes that object's opportunity; it cannot retry or renew. Foreign processes
cannot operate an inherited object. This object is an in-memory fixture controller,
not a durable global activation registry.

The rules always quarantine the collector's interface. Its exact source,
destination and TCP port are allowed only while **both** sets remain active.
Other traffic through the fixture WAN is denied while the blackout is active,
without a destination list or established-flow exemption. Input from the collector
to the host proxy is denied too. This covers tested host/proxy/forwarded TCP,
IPv6 and UDP paths, including the formerly unlisted endpoint and cohosted service.

Normal shutdown flushes both sets in one nftables transaction, then verifies that
both expected sets exist and are empty. The permanent collector quarantine stays
installed. Existing persistent-controller shutdown semantics still serialize with
dispatch and attempt kernel revocation even when the audit write fails. Failed or
unverifiable revocation is never reported as success or automatically retried.
The original timeout remains the fallback.

If the controller crashes or is SIGSTOP-paused, **kernel expiry** removes the
collector's permission first, then restores ordinary traffic without requiring a
userspace watchdog to wake up. The collector remains quarantined after ordinary
traffic resumes. The fixture requires at least one second between expiries, caps
collector permission at 12 seconds and blackout at 20 seconds, and rejects invalid
types/order/bounds before mutation. There is no renewal method.

This is packet permission expiry, not forced process termination or proof that no
response remains in flight. Inbound responses are not all dropped, and application
timeouts or a lost connection can require reconnection after egress resumes. Kernel
failure, host power loss and privileged rule replacement remain outside this result.

## Acceptance

The normal case exercises the full 12/20-second settings and an early terminal
release before the blackout expires. Two independent failure fixtures use shorter
1/4-second settings to observe the gap directly:

1. The persistent controller records preparation, opens an actual collector socket
   using the shared SNAT source, and either exits abruptly or stops itself.
2. After collector expiry, its existing socket is kernel-denied while competitors
   are still blocked. The intended denial counters must increase.
3. After blackout expiry, new direct and proxied competing requests work without
   controller assistance. New collector connections remain denied.
4. A stopped owner resumes only after expiry; its state check fails, it records
   terminal revocation and does not renew or record the uncertain send as success.
   Both failure journals retain exactly one uncertain preparation and no restart
   authority. Each scenario has its own fixture journal; no consumed scope reopens.

There are **35 new Linux checks, 140 total**, and **126 focused Python tests**
(102 controller/harness plus 24 inspector). The 22 new Python cases cover timer
bounds/types, consumed uncertain activation, atomic/idempotent verified revocation,
missing/replaced sets, refusal to retry failed revocation, foreign ownership and
activation/shutdown serialization. Earlier selective-policy counterexamples remain
in the result; broad fixture exclusion does not qualify production-wide coverage.

Commands are unchanged:

```bash
/usr/bin/python3 -I infra/egress-guard/selftest.py
uv run pytest -q tests/ops/test_egress_guard_selftest.py tests/ops/test_egress_host_inspection.py
uv run ruff check infra/egress-guard/selftest.py tests/ops/test_egress_guard_selftest.py
uv run ruff format --check infra/egress-guard/selftest.py tests/ops/test_egress_guard_selftest.py
```

Ruff/format, local links, frozen proposal/contract hashes and diff checks pass.
The full application regression is not rerun for a standalone infrastructure
fixture. Final kernel-tested source SHA256 is
`5669067b880a50c9b7e00a2161d89adcec11f1577feb8edec520e699fce44649`;
deployment remains explicitly unqualified.

## Concrete host proposal and remaining implementation

For the separate single-public-GET bootstrap, the proposed host window is at most
20 seconds of restricted egress, with collector permission expiring at 12 seconds.
The request's existing 10-second deadline and two-second close/archive allowance
must fit the **remaining** permission, including activation/setup delay; late setup
must abort, never extend the window. There is no automatic activation or connection
to the frozen 17-GET joint collector.

This alternative intentionally sacrifices uninterrupted unrelated proxy traffic
during that short window. Proxy access, downloads, API clients, DNS/NTP and remote
management replies using the affected egress may stall. No new address is needed
and no service is stopped by the proposal, but restored network permission does
not guarantee that every interrupted application resumes without intervention.

Before host deployment, implement a separately reviewable source-bound privileged
helper and durable activation state, bind the actual collector/interface/routes and
fixed storage, and verify every real external path, offload/tunnel bypass and
rollout/rollback behavior. The fixture activates its kernel window before creating
the separate request journal; it does **not** yet prove durable global consumption
of a host window before kernel activation. Production must close that lifecycle
gap, including initialization failure and host restart. The optional sudo grant
currently documented permits reading nft rules only, not installing this policy.

Actual deployment also needs explicit acceptance of the interruption and a working
out-of-band recovery path. These are deployment requirements, not reasons to stop
offline implementation. Do not install the literal fixture interfaces/addresses on
the host, delete the collector quarantine while it can still send, assume a
single fixture WAN represents every host path, or silently renew an expired scope.

Broad future exclusion still does not reconstruct past shared-IP usage. The
one-GET bootstrap's unknown-prior-usage exception remains Draft. Existing bootstrap
proposals, the frozen 17-GET / 468-weight joint contract, consumed scopes and
strict continuity **0/14** are unchanged. No host network/proxy configuration,
credentials, upstream source or live trading path was touched.
