# Phase 2 Research Protocol v3

- **Frozen**: 2026-07-12, before accessing any real hashrate, DXY, or VIX factor body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v3.json`
- **Provider contract**: `docs/progress/phase-2-research-v3-data-sources.json`
- **Status**: pre-registered; synthetic validation only.
- **Trading effect**: none.

## Why a new protocol is allowed

The 16-candidate program stop rule remains valid for the opened
price/volume/funding families. Research Protocol v2 remains active but is
blocked on method, entitlement, and incomplete historical archives. Protocol v3
does not reopen, retune, or ensemble any rejected or blocked identity.

It locks three independent data-generating mechanisms before data access:

1. crypto-native miner hashrate recovery;
2. multi-week USD weakness via the Dollar Index;
3. equity implied-volatility relief via VIX.

These drivers are not OHLCV technical rewrites, perpetual funding, taker-flow
share, cross-sectional price rotation, or option-surface substitutes for the
blocked v2 option candidate.

## Economic hypotheses

### Miner hashrate recovery

Network hashrate is a production and security variable, not a price pattern.
When the short-horizon network capacity mean rises above the longer baseline,
miners are re-engaging after stress. The candidate is long-only BTC Spot when
the 7-day mean hashrate is strictly above the 30-day mean; otherwise flat.

### USD weakness impulse

BTC is a USD-priced risk asset. Multi-week USD depreciation can expand foreign
purchasing power and portfolio demand for crypto without requiring a BTC chart
rule. The candidate is long only when the 20-day DXY close-to-close return is
strictly negative; otherwise flat.

### Equity volatility relief

Declining equity implied volatility is a risk-on relief signal in traditional
markets. Because BTC often behaves as a high-beta risk asset, the candidate is
long only when the 5-day VIX close-to-close change is strictly negative;
otherwise flat.

All thresholds are exact zeros. Lookbacks are structural and fixed before any
real factor access. There is no grid, sign flip, universe swap, or
PnL-selected combination.

## Evidence partitions

These match the still-valid anti-overfit calendar used by Protocol v2:

- 2023-2025 is opened and diagnostic-only. No PnL-based selection is allowed.
- 2020-2022 is a one-opening historical replication reserve.
- July 2026 may qualify schemas, publication lag, lineage, and freshness only;
  PnL access is forbidden.
- August-December 2026 is the final future blind. Opening it freezes every
  candidate forever; any parameter change requires a new identity and a new
  future sample.

No candidate may use an opened interval to choose a sign, threshold, lookback,
universe, or ensemble weight. The locked pool contains exactly three candidates.

## Point-in-time input contract

Every observation must carry:

- a unique, strictly increasing UTC `ts_event` at daily frequency;
- `available_at <= ts_event`;
- a non-empty provider `vintage_id`;
- an immutable `sha256:<64 lowercase hex>` snapshot fingerprint;
- finite required numeric factors;
- no forward-filled missing day.

Macro closes (DXY, VIX) are decision-eligible only after the prior session is
published. The locked publication rule is:

- factor body is the previous completed session close;
- `available_at` is no earlier than the next UTC midnight after that session;
- `ts_event` is the decision day 00:00:00Z that uses only already-available
  closes.

Hashrate uses the same daily cadence: the completed UTC-day network estimate
must be available before the decision timestamp that consumes it. Forward
qualification stores exact HTTP/CSV bytes under an immutable envelope. A
present-day revised history may not stand in for the 2020-2022 reserve unless
its publication lag contract is explicit and reproducible.

## Candidate rules

All candidates target BTCUSDT Spot and emit only `buy`/`flat` `SignalEvent v1`
rows on state changes. Every replication fold starts flat; an eligible first
in-fold observation must therefore emit `buy` rather than inheriting an
unobservable pre-fold position.

- **Miner hashrate recovery**: buy only when 7-day mean hashrate >
  30-day mean hashrate.
- **USD weakness impulse**: buy only when 20-day DXY return < 0.
- **Equity vol relief**: buy only when 5-day VIX change < 0.

Zero is always flat. No threshold grid, percentile fitting, sign reversal,
symbol substitution, or PnL-selected combination is allowed.

## Gates and stop decisions

The exact gates live in the machine contract. In addition to positive base and
stress results, candidates need cross-year/month breadth, at least 30 closed
positions, positive leave-best-position PnL, clean long/flat lineage, and exact
rerun reproducibility.

After the one allowed historical opening:

- passing candidates become `replication_pass_pending_future_blind`;
- profitable but undersampled candidates become `insufficient_evidence`;
- every other candidate becomes permanently `reject`;
- no result-driven parameter or ensemble change is permitted.

Only a candidate that subsequently passes the locked five-month future blind
may be considered for `paper_shadow`. This protocol does not change
`SourcePolicy`, run promotion review, restart testnet, load credentials, or
authorize live trading.

## Explicit non-goals

- Do not retune rejected v1 registry models.
- Do not substitute ATM IV, historical volatility, or funding for blocked v2
  option/basis/stablecoin candidates.
- Do not open 2020-2022 or 2026-08..12 during pre-registration or schema work.
- Do not inspect opened 2023-2025 PnL to choose among the three locked rules.
