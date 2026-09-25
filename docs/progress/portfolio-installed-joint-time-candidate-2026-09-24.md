# Installed second-clock candidate

Date: 2026-09-24. Phase: disposable local fixture only. No production key,
venue request, host installation or trading admission is part of this change.

The v24 manifest profile pins the same 26 project-owned sources under new
hashes. A distinct `joint_time` v1 parent adds operation 12, a second fixed
`/api/v3/time` GET after the two route-bound depth-100 attempts. The native
child selects index 12 with the same-run two-symbol route hash and validates
the original TLS time receipt. Parent replay requires both depth successors
and checks that the clock header follows the second snapshot body, stays within
60 seconds of the buffered market events and remains on the same UTC day.
It binds the clock and both snapshot TLS hashes but does not qualify a provider
clock, synchronized OrderBook, QuoteTick, full account interval or stream fence.
Success and bad-server-time scenarios are wired into the disposable fixture;
the latter must consume index 12 without native acknowledgement.

Eight new direct checks plus the 114 prior linked/installed/joint checks pass
(122 total). Ruff lint/format, Python compilation and diff checks pass. The
embedded fixture peer compiles. **Neither v24 scenario has passed the
dedicated-UID namespace acceptance.** The sandbox blocks that fixture, and
the earlier elevated retry was rejected by automatic approval review. The
v23 linked-depth candidate also remains unaccepted at its final source hashes;
the last verified ordered parent is v22 at 11/19. No old v22 or preliminary
v23 report can certify the v24 source inventory.

Next: with explicit authorization for the disposable privileged fixture,
run `--joint-time-profile` success and bad-clock scenarios from a new ignored
report path, validate the final source hashes and original journals, then run
the `--joint-linked-profile` three-scenario and older joint regression profiles
under the same protected source inventory. Only after that can the accepted
prefix be advanced. The remaining planned operations are a second four-GET
account pass, a final clock and account WebSocket unsubscribe. Real gateway
authority, provider usage and clock evidence, complete account coverage and
all trading admission are separate blockers.

## Acceptance update (2026-09-25)

The requested v24 isolated acceptance and same-source regressions are now
complete. The distinct linked-time parent accepts 13/19 steps on success;
the bad clock consumes index 12 without native acknowledgement. The formal
[acceptance record](portfolio-installed-joint-time-acceptance-2026-09-25.md)
and its JSON pin all eight ignored reports and 31 passing scenarios. The
pre-acceptance assessment above is retained as the 2026-09-24 history; the
remaining six operations and real-admission blockers still apply.
