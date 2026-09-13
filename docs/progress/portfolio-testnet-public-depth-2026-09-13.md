# Public BTCUSDT depth reconstruction and bounded probe — 2026-09-13

The detached depth implementation now reconstructs Binance Spot testnet snapshots
and diff updates into native Nautilus `QuoteTick` values. The immutable
[provider contract](portfolio-testnet-provider-coverage-2026-09-13.md) remains the
specification, including its conservative bootstrap boundary. This is single-symbol
historical market evidence; account, valuation, baseline, runtime and order
qualification flags remain false.

## Implementation

- `apps/strategies_nautilus/portfolio_market_depth.py`: pure snapshot/delta book,
  exact native price/size conversion, venue E versus local receipt timestamps,
  update linkage, obsolete/conflicting ranges, freshness and finite snapshot coverage.
- `apps/strategies_nautilus/portfolio_market_depth_archive.py`: durable raw receipts,
  fixed source/profile/epoch, hashes, ordered request/clock/budget validation,
  successful closure seal and detached replay with an explicit original SHA256.
- `apps/ops/portfolio_market_depth.py`: explicit public probe or historical replay.
  No credentials, account requests, order client, execution engine or service.

The first usable update requires `U <= snapshot L < u`. An initial `U=L+1`
is retained as `bootstrap_boundary_unqualified`; later updates use `L+1` linkage.
Old events do not refresh a quote. Deleting the known snapshot frontier cannot
establish the best price in unseen depth. Invalid input, stale/quiet prices,
clock uncertainty, transport loss and persistence failure stop the segment.

Application response/frame bytes are stored as base64 before JSON parsing or
native conversion, preserving even invalid UTF-8. Each row is flushed and fsynced.
An unsuccessful journal cannot be replayed as a completed segment, even if it
contains earlier native quotes. Hashes detect changed selected bytes; they do
not independently authenticate the venue or prove global delivery completeness.

The native WebSocket uses `reconnect_max_attempts=0`, no outgoing heartbeat and
only a matching payload pong for a received ping, limited to five per second.
A real Rust socket against a loopback peer verifies raw frame delivery, ping echo,
and exactly one accepted connection after the peer drops. The native package is
pinned by `pyproject.toml` to NautilusTrader 1.226.0; no upstream source is changed.

Public REST is fixed to `https://testnet.binance.vision` and the ordered sequence
`time → exchangeInfo(BTCUSDT) → depth(BTCUSDT,100) → time → time`: at most five GETs,
weight 28, one stream, zero snapshot/HTTP retries and zero reconnects. Metadata and
shared-IP weight headers must support the remaining budget. Per-request timeout
is 10 seconds, bootstrap 15, collection at most 120 and shutdown 5. Synchronous
fsync and OS/DNS I/O cannot be forcibly preempted by the asyncio deadline; a canceled
HTTP worker may finish its existing bounded request, but cannot start another.
The one-MiB application-frame check runs after native delivery; it does not change
Rust's own internal socket allocation limits. No full-account throughput claim follows.

Archive and report outputs must be new and distinct. The CLI refuses existing
report paths before initiating a probe and never overwrites an existing archive.
For a successful, explicitly selected archive, offline replay is:

```bash
.venv/bin/python -m apps.ops.portfolio_market_depth --replay \
  --archive data/SELECTED-CLOSED-ARCHIVE.jsonl \
  --archive-sha256 SELECTED-ORIGINAL-SHA256 \
  --report data/NEW-HISTORICAL-REPORT.json
```

## Actual bounded attempt

The **single attempt failed with `bootstrap_boundary_unqualified`** and emitted
**zero native quotes**. It started at 2026-09-13 05:42:09.451915 UTC with a 20-second
collection budget and durably recorded its abort 2.916248 seconds later. The CLI
returned exit 1. Four public GET responses (weight 27), one stream connection and
two raw depth frames were retained; no final time request or retry was made.

The first buffered frame was `U=1736713, u=1736722`. The single snapshot had
`L=1736722`, so that frame was correctly obsolete. The next frame was
`U=1736723, u=1736732`: exactly `U=L+1`, which the frozen first-link rule explicitly
refuses. This demonstrates the anticipated bootstrap wording boundary; it is not
proof of a missing venue update, broken WebSocket or stale quote. The two frame
ages at local receipt were 46.057304 ms and 45.671348 ms. The two time samples had
RTTs 137.810970 ms and 118.494552 ms; their apparent offset intervals were
[-43.852697, 94.958433] ms and [-45.530711, 73.963881] ms. Both passed the frozen
clock thresholds. Metadata advertised a 6,000/minute request-weight limit.

| Retained local artifact | SHA256 |
| --- | --- |
| `data/spot-testnet-public-depth-20260913.jsonl` | `f2af2aba60ab0bbde04f37948b7f4d03b0222ec1cd07b36acadd18685eabbfed` |
| `data/spot-testnet-public-depth-20260913-report.json` | `42d9e4d54c911227677bc2fd11f3861bbe6c544228594f85b6e515ba04dc7b23` |

The archive has 20 rows, no completion seal and `locally_linked=false`.
`public_get_responses=4` and `depth_frames=2` count observed receipts;
`validated_depth_frames=1` counts the initial buffered frame, not a usable quote.
An independent CLI process with the pinned archive hash refused replay (exit 1)
and created no success report. The artifacts are ignored local observations and
are not committed. All six qualification flags remain false.

The probe used the tested working implementation based on `7e715f6`. Exact source
bytes below bind that pre-commit run; no implementation changes followed the probe.

| Source file | SHA256 |
| --- | --- |
| `apps/ops/portfolio_market_depth.py` | `bf001478ae0c949a445c64b71758f109c314f9db801bfab94868eb6326816631` |
| `apps/strategies_nautilus/portfolio_market_depth.py` | `2f585d5e39b6f270f7d46a13035f7abd4bfd4f0a6f1ce2c7510c33cab7fd59c0` |
| `apps/strategies_nautilus/portfolio_market_depth_archive.py` | `a622b5d2ff24d3351c8f221affa7fd1892378442cd00ba138cab7e7d95cbd17c` |

Next review the pinned bootstrap wording against this retained sequence offline.
If a different first-link rule is justified, define a prospective, separately
identified contract and its tests before another bounded attempt. Do not edit the
original contract, reinterpret this failed archive as success, or resume this
attempt. Single-symbol success would still not close full-account/UTC/flow/reset
qualification or authorize another ADR-017 order.

## Verification

The 63 focused tests pass. They cover native quantity replacement/deletion and
event/receipt time separation; strict bootstrap, gaps, obsolete/conflicting updates;
malformed prices/frames, wrong symbol/unit, finite coverage, stale/future/quiet data;
clock offset intervals and drift, weight/buffer/archive limits, disk failure;
truncation/unsealed/tampered/rechained semantic evidence; exact public allowlist,
failure cleanup and no retries; real native ping/connection behavior; and two
fresh replay processes producing byte-identical numeric native quote reports.

Full offline regression: **2,760 passed, 12 deselected in 215.58 seconds**
(`-m 'not network and not postgres'`). The final receipt-count/quote-age reporting
refinements then passed the same 63 focused tests in 5.25 seconds. Ruff passes for
all `apps/` and `tests/`; the research registry check passes. The original provider-contract JSON hash is checked by a test:
`376eebff8fd2309027df2334f39d3ec73fd017f6a8afff1b3f0e3ea3023d879e`.

The fixed private `native.json` SHA256 still matches its original
`08995a8289a99b88e02f87c9c07387302c8f74ed006e5a2a33ddf1932d0b1a5f`.
No private session file, permission, risk policy, SourcePolicy, schedule, runner
or live order path is changed. ADR-017's BUY/cancel allowance remains consumed.
ADR-015/016 full-account/UTC/flow/reset qualification and strict 0/14 remain blocked.
