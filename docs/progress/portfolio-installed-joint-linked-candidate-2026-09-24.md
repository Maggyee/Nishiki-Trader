# Installed two-symbol snapshot linkage candidate

Date: 2026-09-24. Phase: disposable local fixture only. No host installation,
real venue request, production key or trading permission was used.

The v23 source inventory retains 26 protected project-owned sources. A new
`joint_linked` v1 scope holds the account and market sockets, archives four
bounded raw market frames (two per selected symbol) before accepting step 9,
and requests the `BNBUSDT` and `BTCUSDT` depth-100 snapshots at steps 10 and
11. Parent replay checks the originals, receive clocks, per-symbol revision
continuity and snapshot successor linkage. It does not create a synchronized
OrderBook, QuoteTick, account interval or stream fence. The old v22 first-depth
scope remains a separate 11/19 acceptance.

Nine new direct tests, 35 installed-gateway tests and 70 joint-depth/read/WS
tests pass; Ruff lint/format, compile and diff checks pass. An additional
broader test run passed 159 cases but encountered 99 setup errors when the
sandbox denied `SO_PASSCRED`; those cases are unverified here. The earlier
ignored `data/joint-linked-v23-acceptance-20260924-b.json` recorded success
at 12/19, a gap at 9/19 and a crossed second book at 11/19, but its manifest
was v22 and its source bytes predate the final market-frame byte limit. It is
not evidence that the current v23 sources pass isolation.

The v23 acceptance attempt produced no report: sandbox `no_new_privileges`
blocked the dedicated-UID setup, and an elevated retry was rejected by
automatic approval review. Do not infer a 12/19 accepted milestone from the
unit tests or the old report. The next verification step is a separately
authorized disposable local fixture run of all three `--joint-linked-profile`
scenarios with the final source hashes, followed by the v22 depth, v21 market,
v19 read, clock, account-WS and unsubscribe regressions. After that, remaining
steps are linked time, a second four-GET account pass, final clock and
unsubscribe. Complete before/after account coverage, real gateway authority,
provider clocks/usage and all trading admission remain blocked.

## Acceptance update (2026-09-25)

The final v23 candidate did not receive an isolation report. Its successor,
the v24 source inventory, passes all three linked-depth regressions: success
accepts 12/19; a market increment gap stops at 9 and a crossed second book
stops at 11. The same inventory passes the later second-clock acceptance at
13/19; see the [v24 acceptance record](portfolio-installed-joint-time-acceptance-2026-09-25.md).
These results do not retroactively certify the preliminary v22-source report
or a v23 isolated run. The incomplete account interval and real-admission
blockers above still apply.
