# Installed first joint clock operation

Date: 2026-09-24. Phase: disposable local fixture only. The
[machine-readable summary](portfolio-installed-joint-clock-2026-09-24.json)
pins the ignored full original reports. No host installation, venue request,
production credential or trading permission was used.

Manifest v17 pins 23 project-owned sources, adding `gateway_native_time.py`.
A new parent scope accepts only the fixed `clock_initial` step at index zero;
preparation consumes the scope before the single marked HTTPS GET to
`/api/v3/time`. The dedicated UID selects the unsigned request through the
pinned channel. Root verifies its selector, retains original TLS chunks and
receive clocks, revokes kernel permission, and delivers the exact response to
the isolated native runtime. The native clock receipt binds the server time
to the original root receive time within the local five-second fixture window.
It does not qualify a provider clock or source authority.

Both actual namespace scenarios pass. `clock_success` accepts one ordered
joint operation and one native clock receipt. `clock_bad_time` consumes the
attempt but accepts zero operations, returns `incomplete_no_resume` and has no
native receipt. Both make exactly one local GET, refuse fresh-process restart,
and leave at least 210 descriptors spare under the unchanged 1,024 cap. The
two v16 unsubscribe success/failure scenarios also pass against the v17 source
inventory. Eighty-four focused Python tests pass, including malformed clock
payloads and account/ledger/handoff regression coverage.

This is **one operation of the 19-operation dual-symbol plan**, not a complete
account interval. The earlier six-read route parent and v16 unsubscribe scope
are separate and cannot be concatenated into this new parent. Next add the
fixed account WS connection and signed subscription to this same ordered
parent, then both complete four-GET account reads, metadata/routes, market
bootstrap, linked time samples and unsubscribe. Stream fences, provider usage,
shared egress coverage, qualified equity, host rollout and all trading remain
blocked. No consumed scope may be reopened.

To repeat with a new disposable path:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py \
  --joint-clock-profile --report data/NEW-JOINT-CLOCK.json
```
