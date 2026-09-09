# Nautilus portfolio lifecycle acceptance — 2026-09-09

Status: **synthetic offline lifecycle acceptance implemented** for the v2 funded
admission contract. This completes the next engineering increment; it is not
paper_simulated promotion, an allocation decision, or portfolio return evidence.

## Implemented boundary

`apps.strategies_nautilus.portfolio_simulation.PortfolioSimulationStrategy`
uses NautilusTrader 1.226.0 `Strategy`, `RiskEngine`, `ExecutionEngine`, and
`BacktestEngine` extension points. Nautilus owns all orders, fills, balances and
positions. Project code supplies a conservative admission/reservation adapter
and a durable intent/audit journal, never a second matcher or execution ledger.

The isolated harness accepts only synthetic SignalEvent v1 identities
`rule_fixture_v16/v18/v22/v34/v36`, model `portfolio-lifecycle-fixture-v1`, under
`TestClock`. No legacy source is authorized by this fixture allowlist. The
existing SourcePolicy, collector jobs, MARKET baseline runners and runtime risk
settings are unchanged. No credentials, exchange adapters, research bundles or
future blind data are loaded by the harness.

The fixed synthetic instrument is BTCUSDT.BINANCE, CASH/HEDGING, 500 USDT and
zero BTC, 0.001 BTC per sleeve, bounded LIMIT at 100,000 USDT, quote fees of
15 bps. This fee is a fixture setting, not a current exchange fee estimate.
The five frozen sleeve names label engineering fixtures only.

## Admission, accounting and recovery

- Signal inputs are schema-revalidated, then checked for source/model, venue,
  instrument, confidence, TTL and supported buy/flat semantics. IDs and per-sleeve
  event-time watermarks persist. The newest eligible signal supersedes older
  same-batch signals; competing signals at the newest identical timestamp reject
  that sleeve. Duplicate IDs within a batch fail closed. Skipped signals are
  consumed without a retry queue. Quantities come only from the strategy.
- Native positions must reconcile exactly to settled account BTC. Native orders
  must match prepared quantity, price, side, tags, strategy and position ID.
  Unknown orders, unowned positions, unexpected assets or stale quotes block
  admission. Snapshot cash is native total/free balance with conservative fee
  reservations; an unfilled sell never credits cash to the same batch.
- One non-yielding section on the owning simulation thread runs selection and
  prepares **all** selected orders before any submit. A process file lock enforces
  a single checkpoint writer. Nested and foreign-thread admission are rejected.
  Each prepared intent reserves its full amount until native cache acknowledges
  progress. The complete batch is fsynced and atomically replaced on disk before
  the first native submit. A submit/disk exception halts new admission and retains
  uncertain reservations. Prepared does not mean accepted or filled.
- Native partial fills reduce only the unfilled remainder. Cancel requests retain
  reservations until a terminal native acknowledgement; actual fills arriving
  while cancellation is in flight remain accounted for. Native RiskEngine denial
  is authoritative even after successful project preflight. Duplicate or late
  strategy callbacks only audit native events; they cannot apply cash a second time.
- The journal stores version/config fingerprints, integrity checksum, original
  signals, consumed IDs, intents, event audit, day baseline, peak and risk latch.
  It stores no reconstructed execution balances. Warm strategy replacement
  reuses the retained native cache/account and verifies its intents. Missing
  native state on cold restart is refused, with no automatic resubmission.
- Inclusive synthetic 50 USDT daily and 250 USDT fixed peak-loss thresholds latch
  entry rejection. Fresh reconciled owned reductions remain possible. A price
  recovery, new UTC day or strategy restart never clears the latch.

## Acceptance evidence

The CLI smoke scenario selects v16/v18/v22/v34 and explicitly skips v36. It
reserves **400.60 USDT** and exposes **99.40 USDT** to the next batch, which
cannot afford another unchanged buy. After warm strategy replacement and native
fills the account holds 0.004 BTC / 99.40 USDT. A v18 flat signal closes only
that sleeve, yielding 0.003 BTC / 199.25 USDT. These are synthetic accounting
assertions, not investment returns. Two independent runs return identical reports.

Focused tests additionally exercise partial/late fills, delayed cancellation,
same-batch sells without cash pre-credit, native risk denial, durable preparation,
interrupted first/second submits, failed checkpoint replacement, unknown orders,
checkpoint corruption, concurrent writers, signal supersession, replay/expiry,
foreign threads, stale marks, and daily/peak loss latches across restart and UTC
rollover. Tests use real Nautilus simulated fills and balances; no custom fill
simulator is introduced.

Reproduce without network or retained research inputs:

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_simulation_acceptance
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_simulation.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
```

The CLI uses a temporary checkpoint and removes it after producing the JSON
report. Tests retain isolated checkpoints only in pytest temporary directories.
Verification: **35 focused tests** and **1,833 full offline tests** passed;
12 Postgres integration tests were deselected because no dedicated test DSN was
supplied. CLI smoke, Ruff lint/changed-file formatting and registry check passed.

## Remaining implementation and review

1. This is single-threaded backtest acceptance, not a production transaction or
   account adapter. Full process recovery needs a durable native cache, authoritative
   account/venue reconciliation, and an explicit resolution of uncertain submits.
   The checksum detects accidental corruption; it is not an anti-rollback or
   authentication mechanism. Losing all journal/native history is unsupported.
2. Only fixed synthetic LIMIT constraints and quote fees are attached. Effective
   venue trading status, dynamic price bands, order-count limits, changing fees,
   transfers and unrelated assets still need an authoritative adapter and tests.
3. The daily baseline is the first observed synthetic quote of each UTC day;
   fixtures start at UTC midnight. This is not gap-safe reconstruction of an actual
   account's midnight equity. Risk is sampled on quotes/admission; there is no
   production account-event kill switch or automatic emergency cancellation here.
   Restart or corruption recovery never grants a latch reset.
4. The 50 USDT planning limit remains offline. Reconcile it with ADR-001/002's
   binding runtime 5% daily rule before any runtime policy change. This increment
   does not alter that rule or any paper/testnet/live runner.
5. Before wall-clock paper promotion, perform the separate portfolio-level alpha
   and prospective evidence review, including deterministic admission bias against
   later sleeves. Earlier retained-basket PnL is not v2 performance evidence.
   Testnet/live gates remain blocked and the sealed future PnL remains unopened.

No upstream source was modified. The prior v1/v2 contract artifacts remain
immutable historical records; this acceptance record describes the new wiring.
