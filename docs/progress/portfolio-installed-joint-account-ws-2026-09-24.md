# Installed ordered joint account WebSocket prefix

Date: 2026-09-24. Phase: disposable local fixture only. The
[machine-readable summary](portfolio-installed-joint-account-ws-2026-09-24.json)
pins ignored original reports under `data/`. No host installation, real venue
request, production credential or trading permission was used.

Manifest v18 pins 24 project-owned sources, adding `gateway_joint_account_ws.py`.
One single-use parent accepts the fixed `clock_initial`, `account_connect` and
`account_subscribe` steps in that order. The initial clock GET keeps its original
HTTPS clocks and isolated native acknowledgement. Root retains one verified
account TLS socket across the Upgrade and subscription steps. Each step records
its intent before the kernel mark is granted, persists raw response chunks and
receive clocks, revokes the mark and only then lets the parent replay and accept
the original bundle. The dedicated UID signs the fixed subscription selector;
its runtime and process constraints are checked against the prior clock original.
Root neither loads NautilusTrader nor constructs an account snapshot.

All three actual namespace scenarios pass. `joint_success` accepts three steps
with one verified Upgrade and signed subscription reply. `joint_bad_ack`
consumes the third attempt but accepts only the first two steps. `joint_bad_time`
consumes the initial attempt, accepts no steps and never starts account WS.
All refuse a fresh-process restart of their consumed parent, reject marked
traffic after termination and leave at least 208 descriptors spare under the
unchanged 1,024 limit. The existing v17 clock and v16 unsubscribe scenarios
also pass with final v18 sources. Across the relevant regression modules, 302
Python tests pass; these include rehashed original tampering and revoked
prefixes. A combined pytest invocation caused 20 snapshot tests to lose their
fixture due to plugin registration order; all 20 pass when run as their own
module. This is a test invocation limitation, not an acceptance bypass.

This is **3 of 19 planned dual-symbol operations**, with zero account events,
zero complete account intervals and no stream fence. The isolated v16
unsubscribe and old route/snapshot receipts cannot be appended to this parent.
Next add both complete four-GET account reads under this same ordered parent,
then metadata/routes, market bootstrap, depth/time steps and unsubscribe.
Provider limits and clocks, shared egress coverage, qualified equity, host
rollout and all real trading remain blocked. No consumed scope may be reopened.

To repeat with a new disposable path:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py \
  --joint-account-profile --report data/NEW-JOINT-ACCOUNT.json
```
