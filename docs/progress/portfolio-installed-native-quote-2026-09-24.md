# Installed fixture native L2 and QuoteTick receipt

Date: 2026-09-24. Phase: disposable local fixture acceptance only. The
[machine-readable result](portfolio-installed-native-quote-2026-09-24.json)
pins the ignored report and native runtime hashes. The v15 manifest pins 22
project sources; no base installation, host code or real scope changed.

The new quote route parent and WS child consume their own scopes. The fixed
local peer serves two buy levels and one sell level per selected symbol. A
buffered update is obsolete at snapshot revision 101; the eligible update
deletes the best buy at 100 while leaving the 99 level. Root retains the raw
HTTPS/WS chunks and checks snapshot linkage, event clocks, nonempty sides,
spread and bounded snapshot coverage. After socket closure and kernel
revocation, the dedicated UID independently constructs NautilusTrader L2 books,
applies the exact original-derived native deltas and acknowledges two native
QuoteTicks at bid 99 / ask 101. Their `ts_init` is no earlier than the later
snapshot/event receipt. Root imports no Nautilus code.

Three installed scenarios pass their expected outcomes: one complete quote
receipt (102 checks), and empty-buy and crossed-book refusals (97 checks each).
Both refusals leave the WS archive `incomplete_no_resume` with no native quote
acknowledgement, while the parent six-read route archive remains complete.
The maximum sampled controller descriptor count is 856 under the unchanged
1,024 limit. Thirty-six focused tests cover existing snapshot behavior, v14
handoff pins and root/native quote parity, including original, time and
revision drift. The old v14 report still hashes to
`7b0e035ddaddd907bb46678a4e55012c94b7c2de9c56df562738ca94a6b68547`;
its direct and two-hop handoff replays still return
`blocked_incomplete_joint_collector` with zero historical QuoteTicks.

This is a bounded fixture book receipt, not a gap-free stream fence, real
account/source authority, qualified price or executable observation. The
installed route/snapshot fixture still provides eight REST GETs versus 15 in
the full dual-symbol plan; three time, two account and two open-order GETs,
plus account unsubscribe, remain unimplemented in the installed ordered
collector. Zero complete account intervals and zero ordered joint operations
are accepted. Real shared-egress coverage, provider usage/clocks, host rollout
and all trading remain blocked.

Reproduce with a new report path in an authorized disposable namespace:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py \
  --quote-ws-profile --report data/NEW-QUOTE-WS.json
```
