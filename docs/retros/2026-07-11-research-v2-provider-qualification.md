# 2026-07-11 Research Protocol v2 Provider Qualification

- **Status**: Forward option/basis coverage qualified at 7/7; one candidate
  data route remains blocked and no candidate is replication-ready.
- **Scope**: schema, availability, immutable lineage, and publication-interface
  qualification only.
- **PnL accessed**: no.
- **Trading effect**: none.

## Pre-access lineage

The candidate identities, rules, partitions, and gates were committed and
pushed in `88c8acb` before any provider response body was fetched. Exact public
requests and the raw-snapshot contract were committed and pushed in `d18da5c`
before the first response body was fetched.

Qualification then found three provider/interface facts without computing
returns:

1. Deribit includes some same-day deep-out-of-the-money options with zero mark
   price. Rows remain in the immutable raw snapshot, but zero marks are not
   counted as usable positive-mark surface observations.
2. Binance COIN-M `exchangeInfo` uses `contractStatus`, not `status`.
3. Coin Metrics Community returns HTTP 403 for USDT 1d `TxTfrValUSD`.

The first two corrections changed only schema validation and were committed in
`081ffcc`; candidate signs, thresholds, identities, cost assumptions, evidence
partitions, and gates did not change. The stablecoin candidate was not switched
to free `TxCnt` or `AdrActCnt`, because doing so after pre-registration would
change the economic mechanism.

## Immutable-envelope correction

The first successful option and basis draft files hashed exact HTTP bytes but
retained only parsed JSON. Their payload hashes could not be independently
recomputed, so both drafts are excluded from eligible lineage:

- `data/research-v2/raw/options-20260711T030158Z-502612e84038.json`
- `data/research-v2/raw/basis-20260711T030158Z-44b61231ae6f.json`

Commit `4b2b8fb` corrected the envelope before replacement collection. Eligible
snapshots retain exact response bytes as base64 and independently verify:

- raw-byte SHA-256;
- raw JSON equals the stored parsed payload;
- provider-specific audit summary;
- canonical envelope SHA-256;
- vintage id and filename hash prefix;
- all read-only/no-PnL boundaries.

Tests deliberately mutate the parsed payload and confirm verification fails.

## Qualified snapshots

### Deribit BTC options

- Path: `data/research-v2/raw/options-20260711T030413Z-6f136e6e5808.json`
- Snapshot SHA-256:
  `sha256:6f136e6e58081c06bd5f7ead7108d4aaff88052c8e1bfd23b794646e90311b9c`
- Contracts: 876
- Expiries: 12
- Two-sided positive-mark contracts: 797
- Zero-mark contracts retained but ineligible: 9
- Offline verification: `valid=true`

This qualifies the current-surface schema and forward immutable collection. It
does not provide a historical point-in-time surface and does not yet implement
the structural expected-return replication required by the candidate.

The public-method availability check found only the abstract, conference
summaries, and a request-full-text page. Direct SSRN CLI retrieval returned
HTTP 403, and no author/institution copy or public implementation was found.
The abstract establishes that the paper uses a flexible structural
arbitrage-consistent risk-neutral distribution and that higher-order moments
and volatility-of-volatility matter; it does not disclose enough calibration
detail to reproduce the model. The option candidate is therefore additionally
`blocked_method_replication`. No model-free smile fit, ATM-IV threshold, or
invented coefficient is allowed as a substitute.

### Binance COIN-M quarterly basis

- Path: `data/research-v2/raw/basis-20260711T030413Z-5254aac625b5.json`
- Snapshot SHA-256:
  `sha256:5254aac625b56c353c580663655241376dae3de332f5ab1a2c5dd65fd3ee329b`
- Current quarter: `BTCUSD_260925`
- Next quarter: `BTCUSD_261225`
- Contract state: `TRADING` for both, with ordered future delivery dates
- Offline verification: `valid=true`

This qualifies current/next mapping and the forward daily basis interface. The
public endpoint exposes only recent observations and cannot establish the
2020-2022 point-in-time replication reserve by itself.

An official Binance public-data archive metadata audit then tested whether the
locked reserve could be reconstructed without a vendor. It used S3 LIST key
and size metadata only and did not read ZIP or CHECKSUM bodies. Findings:

```text
status=blocked_incomplete_historical_reserve
required_months=36 (2020-01 through 2022-12)
first_available_index_month=2020-06
missing_zip_months=2020-01..2020-05
missing_checksum_months=2020-01..2020-05
prices_read=false
pnl_computed=false
```

The archive contains 26 valid quarterly BTCUSD contract prefixes, one malformed
date prefix (`BTCUSD_220631`), and the correctly excluded non-quarterly
`BTCUSD_PERP` prefix. File keys also persist after contract expiry, so key
existence alone cannot establish valid rows. The missing first five index
months already makes the locked three-calendar-year gate impossible; price
bodies were therefore left unopened. Partial 2020 cannot be relabeled as a
full year and opened 2023 cannot be substituted.

The verified snapshot also passed the PnL-free factor transformer. Its
retrieval at `2026-07-11T03:04:13.557781Z` maps to a deliberately delayed
decision timestamp of `2026-07-12T00:00:00Z`. The qualification report contains
one row and records `returns_loaded=false`, `signals_generated=false`, and
`pnl_computed=false`. No factor CSV was written during dry-run.

The paired multi-snapshot coverage reviewer also ran against the eligible
option and basis snapshots. Result:

```text
status=collecting_insufficient_days
paired_day_count=1
minimum_contiguous_days=7
paired_dates=[2026-07-11]
blockers=[]
recommendation=continue_daily_snapshot_collection
```

Both kinds have exactly one verified snapshot on the same UTC date with no
internal gap or duplicate. The result is deliberately not a pass. Coverage
qualification requires seven exact paired consecutive dates and still does not
authorize signal generation or PnL access.

### Seven-day forward coverage completion

The credential-free cloud collector completed the locked forward window on
2026-07-17 under attempt `attempt-20260711-001` and image/git SHA
`5a8289c50f89fb1a2ae9e1aaf5b69a12d2287fcb`:

```text
status=qualification_coverage_pass
paired_day_count=7
paired_dates=2026-07-11..2026-07-17
options_unique_day_count=7
basis_unique_day_count=7
ledger_rows=14
duplicate_dates=[]
missing_dates=[]
unpaired_dates=[]
blockers=[]
recommendation=factor_pipeline_qualification_allowed_without_pnl
```

The server wrote `COMPLETE` at `2026-07-17T03:15:10.618077Z`. Later timer
triggers were skipped by the systemd `ExecCondition`, so no additional network
or container work ran after completion. The completion record preserves all
read-only boundaries: prices were not summarized, returns were not loaded, PnL
was not computed, signals were not generated or written, Nautilus was not run,
and SourcePolicy was not mutated.

This supersedes only the earlier `collecting_insufficient_days` coverage state.
It does not remove the option-method replication blocker, the incomplete basis
historical reserve, or the stablecoin entitlement blocker.

### Coin Metrics stablecoin liquidity

- Requested locked universe: USDT + USDC
- Requested locked metrics: `SplyCur` + `TxTfrValUSD`, daily
- Result: HTTP 403 because USDT `TxTfrValUSD` is not available on Community
  credentials
- Snapshot: none
- Decision: `blocked_provider_entitlement`; no metric substitution

The public catalog shows Community coverage for supply, transaction count, and
active addresses, but those are not the pre-registered transfer-value factor.
Historical replication also requires genuine point-in-time vintages rather
than a present-day revised history.

## Boundary audit

Both qualified snapshots record:

```text
credentials_loaded=false
pnl_computed=false
signal_store_written=false
nautilus_run=false
source_policy_mutated=false
```

No SignalEvent was generated, no backtest was run, no historical reserve or
future blind was opened, no credentials were loaded, and no testnet/live state
changed.

## Decision and next entrypoint

- `option_risk_premium`: provider schema qualified; historical archive and
  full method/code, historical archive, and structural replication pipeline
  still required.
- `futures_basis_curve`: current provider schema and one-snapshot point-in-time
  transformation qualified, but historical replication is
  `blocked_incomplete_historical_reserve`; continue forward snapshots without
  opening historical price bodies.
- `stablecoin_liquidity`: blocked until licensed transfer-value plus
  point-in-time vintage data exists.

No candidate is yet usable or eligible for historical replication. Keep the
2020-2022 reserve closed. The next safe implementation is a passive directory
audit plus factor transformer for the two qualified snapshot families, followed
by repeated July schema/freshness collection; it must still not compute returns
or strategy PnL.
