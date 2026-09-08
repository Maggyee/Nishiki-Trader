# Forward acceptance and event-cash progress — 2026-09-08 v3

The operator requested continued progress. This increment verifies naturally
scheduled forward runs and closes the daily-sampling gap for **recorded-fill
cash settlement**, without changing the 500 USDT / 50% / 50 USDT planning budget,
positions, SourcePolicy or trading permissions. Matching JSON is schema v3;
earlier reports remain immutable.

## Latest actual collector runs

At the morning check after 07:27 UTC, all nine collectors whose September 8
jobs had become due had successful latest attempts under the pinned `1727408`
deployment. V16's latest successful record is September 7 at 12:30 UTC; its
September 8 job is not due until 12:30 UTC. The ten cron entries still match
the deployment receipt and the deployment checkout is clean.

V22/v34/v36 each now have **two corrected successful attempts on one UTC date**:
the initial smoke and their natural cron execution. Their distinct qualified-day
count remains one, with zero new forward signals; same-day re-execution did not
inflate evidence. Stored signal totals remain 37 / 36 / 45. Both corrected
attempts per pipeline pass snapshot/BTC hash, identity and journal-count checks.

The latest ten-candidate overview is in JSON. Historical blockers are preserved,
including v8's past anomalies despite its nine qualified dates. No candidate has
unblocked review eligibility. No additional manual collection or new job was
used to create this progress; the runtime monitor was refreshed from retained
statuses only. Genuine time and new observations still have to accumulate.

## Execution-event cash accounting

The [fixed method](portfolio-event-cash-method-2026-09-08.md) uses only the six
previously verified primary Nautilus fill paths on 2023–2025. It rechecks fill
hashes and lineage before accounting and reconciles final cash to previously
reported basket PnL. Missing-provenance candidates are never silently included.

There are **491 distinct timestamps**, including **70 mixed buy/sell timestamps**.
Independent runs do not establish cross-strategy ordering for ties. Both
sell-before-buy and buy-before-sell cash requirements are therefore shown.

| Cash requirement, USDT | Raw six-sleeve basket | Existing duplicate-normalized diagnostic |
| --- | ---: | ---: |
| Base costs, sells first | 387.14 | 308.85 |
| Base costs, buys first | 389.55 | 311.26 |
| Stress costs, sells first | 395.66 | 320.51 |
| Stress costs, buys first | 398.19 | 320.51 |
| Stress cash headroom at 500 USDT, buys first | 101.81 | 179.49 |

The raw conservative stress requirement is 2.53 USDT higher than the previous
daily sampled 395.66 USDT figure. The fixed 500 USDT budget still covers both
recorded-fill settlement bounds. This is **not** approval of an executable
portfolio: outstanding-order reservations, actual account segmentation,
transfer delays, venue constraints and intraday market-value drawdown are not
modeled. No new fills, external prices, strategy returns or allocations were
generated. Increasing the precision of cash accounting does not prove alpha.

## Changed files and verification

- Added `apps/ops/research_portfolio_cash.py` and 11 regression tests in
  `tests/ops/test_research_portfolio_cash.py`.
- Extended `apps/ops/research_strategy_followup.py` with event cash bounds,
  hash/lineage revalidation, PnL reconciliation and daily-bound consistency checks.
- Tests cover hidden same-day cash needs, ambiguous buy/sell ties, input-order
  invariance, fee treatment, retained profits, duplicate normalization, and
  invalid/future/duplicate/negative cash inputs. The focused suite has 32 passes.
- Ruff and the family registry check passed. Real v3 evaluation returns expected
  partial status because provenance and forward acceptance remain incomplete.
- Full offline suite: **1,711 passed**, 12 Postgres integration tests deselected
  (no dedicated integration DSN supplied).
- Added the event-cash method and this versioned JSON/Markdown report; updated
  project status and reading list. No upstream source touched or live-path impact.
- No collector runtime code changed, so no redeployment or cron change is needed.

Remaining external requirements are the original audit references for four
candidates (plus clean eligible evidence for v42), genuine future dates and
verified account equity. Next cash feasibility work must distinguish retained
fill settlement from open-order cash reservations; it must not label one as the
other or use these diagnostics to authorize trading.
