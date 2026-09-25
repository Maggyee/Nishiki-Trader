# v27 installed joint-profile regression

Date: 2026-09-25. Eight historical joint profiles were run against the current
v27 protected-source inventory in separate disposable local namespaces. This
closes the previously unrun **joint-profile** isolation regression noted in the
[v27 acceptance](portfolio-installed-joint-complete-acceptance-2026-09-25.md).
The original v27 success and bad-ack report remains unchanged; these are fresh
scopes and do not reopen any earlier scope.

| Profile | Scenarios | Ignored original report SHA256 |
| --- | ---: | --- |
| `--joint-clock-profile` | 2 | `601c95681ac06a3b96860893f8ff4171e222344b7294183ca8028cc13cd05541` |
| `--joint-account-profile` | 3 | `590a52528319dcadedf3f09fd4d61e9c6c71fcedc828269f677f9b915d833c98` |
| `--joint-reads-profile` | 5 | `d376827c5fa45355efc58048732f4aafe2bab2404eb863791c80ba57ae4ebda6` |
| `--joint-depth-profile` | 2 | `f6dd325bb4c7faa08bf82f84706c5ea77d256b12d506b2d4fec3c7ff03d5fa1a` |
| `--joint-linked-profile` | 3 | `001aebaf9f6f2377a25b8dc16475f24313796f702dfb01c20bd30b55f56fb538` |
| `--joint-time-profile` | 2 | `cd7403b5301ee7f9ef7de6dac8061e7df2509c5dc1e57d34a456ad480f334782` |
| `--joint-after-profile` | 3 | `b63d40f7072b4340786abac3f0749e8981559535df2641086062d43e7f74721c` |
| `--joint-final-profile` | 2 | `aeb405cd95a7033f011fd98fe5b2e14b270a90e2b42f2384061cf320d7cda881` |

Each report is an exclusive ignored file at
`data/installed-joint-<profile>-v27-regression-2026-09-25.json` (the account
file uses `account-prefix`). All **22 scenarios pass**. Successes accept the
expected 1, 3, 10, 11, 12, 13, 17 and 18 ordered steps; malformed clocks,
subscriptions, repeated account reads, books, market Upgrade and increment
links retain the preceding accepted prefix and refuse the next step. Each
report contains the original sequence replay and per-scenario terminal result.
Every report has 26 source hashes equal to the original v27 success report;
the harness source hash also matches. Runtime bundles are built per run and
are individually pinned; their archive hashes are not claimed to be identical.
All reports say host observations were restored, venue requests were zero,
and network/trading admission remains false.

The related Python regression across ten ops test modules passes **167 tests**
when `SO_PASSCRED` is permitted. The same run in the restricted sandbox had
145 passes and 22 fixture setup errors at `SO_PASSCRED`; those errors are an
environment restriction, not failed test assertions. These runs do not certify
the older non-joint profiles from the historical 31-scenario v24 aggregate,
host installation, real all-caller coverage, provider usage/clock bounds or
the actual 502-asset account. No detached fresh-process replay of these eight
new reports was run beyond their built-in original sequence reviews.

Next use the existing installed UID/IPC custody and offline admission arithmetic
to develop a prospective authenticated source/egress evidence boundary. It must
independently establish complete caller history and enforce other-caller bounds
before a real first request; these fixture reports cannot supply that evidence.
Consumed bootstrap/depth/ADR-017 scopes and the frozen 17-GET joint draft remain
unchanged. No upstream source, credential, production host or live order path
was modified by these regressions.
