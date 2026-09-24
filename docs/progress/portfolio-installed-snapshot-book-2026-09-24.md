# Installed snapshot historical book reconstruction

Date: 2026-09-24. Scope: offline review in the ordinary project process. The
[machine-readable result](portfolio-installed-snapshot-book-2026-09-24.json)
selects the ignored v14 installation report by SHA256. No fixture scope was
reopened; no venue request, credential, socket or installed native child was used.

`apps.ops.portfolio_installed_snapshot_book` first runs the full installed
handoff's protected-source and original-byte replay. It then reparses each
verified HTTPS snapshot, builds a NautilusTrader native L2 book from its
eight-place levels, and applies only the verified first eligible original depth
increment(s). Each native delta is reconstructed and compared exactly. At every
update, the reviewer checks sequence linkage, both book sides, spread, bounded
100-level snapshot coverage, snapshot age and event age. A QuoteTick's `ts_init`
is the later of the snapshot and event receipt clocks; a buffered event cannot
make a quote available before its snapshot was received. Recovered later levels
do not erase an earlier empty or crossed book. A quote is returned only if every
selected symbol passes the whole bounded segment.

Both installed success scenarios remain **blocked**. Their four per-symbol
books each start with one buy and one sell level; the first nonobsolete update
deletes the only buy level, leaving `empty_bid`. No QuoteTick is produced. The
event-to-availability ages are 298–421 ms, within the five-second local test
bound; stale time is not the cause. An isolated synthetic two-sided sequence
does construct an exact native QuoteTick, including the later snapshot receipt
as `ts_init`. Twelve focused tests cover the valid case, empty/crossed or stale
books, restoration after an empty book, original/revision drift, root refusal and native
delta identity. The existing installed originals and v14 claims are unchanged.

This check does not create a native acknowledgement in the installed gateway,
prove a continuous stream fence or qualify a real market price. Next use a
**new, separate disposable fixture scope** with sufficient snapshot book depth
and nonempty post-update sides, then bind its native receipt after closure and
revocation. In parallel, the complete joint collector still needs the seven
missing GETs, account unsubscribe and a genuinely ordered installed flow.
Real source authority, shared egress coverage, provider limits and all trading
admission remain blocked.

Reproduce each historical review with the pinned report:

```bash
.venv/bin/python -m apps.ops.portfolio_installed_snapshot_book \
  --report data/installed-snapshot-ws-2026-09-23/final.json \
  --report-sha256 7b0e035ddaddd907bb46678a4e55012c94b7c2de9c56df562738ca94a6b68547 \
  --scenario snapshot_success
```

The other accepted selector is `--scenario snapshot_two_hops`.
