# Phase 5 Multi-Candidate Forward Paper-Shadow Portfolio Report

- **Generated at**: 2026-08-24 01:56:29 UTC
- **Total Candidates Tracked**: 10
- **Active Shadow Data Streams**: 7
- **Overall Average Correlation**: 0.1124

## 1. Candidate Roster & Progress

| Protocol | Strategy / Model | Category | Gate Progress | Signals (Buy / Flat) | Shadow Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **V8** | `cboe-gvz5obs-negative-1d-v1` | Commodity / Gold Vol | 5 / 7d | 40 (20B / 20F) | `paper_shadow` |
| **V16** | `treasury-nominal10-absdiff5-20-negative-lag2d-v1` | Fixed Income / Duration | 4 / 7d | 96 (48B / 48F) | `paper_shadow` |
| **V18** | `cboe-vxn-ohlc5obs-negative-1d-v1` | Equity Tech Volatility | 3 / 7d | 42 (21B / 21F) | `paper_shadow` |
| **V22** | `cboe-cor1m-diff5-negative-lag1d-v1` | Option Surface / Correlation | 1 / 7d | 0 (0B / 0F) | `paper_shadow` |
| **V34** | `cboe-fvx-diff5-negative-lag1d-v1` | Fixed Income / Yield | 3 / 7d | 0 (0B / 0F) | `paper_shadow` |
| **V36** | `cboe-vpn-diff5-negative-lag1d-v1` | Option Strategy / Variance | 3 / 7d | 0 (0B / 0F) | `paper_shadow` |
| **V40** | `cboe-vxn-diff5-negative-lag1d-v1` | Equity Tech Volatility | 7 / 7d (Gate Met) | 20 (12B / 8F) | `paper_shadow` |
| **V42** | `cboe-vix6m-diff5-negative-lag1d-v1` | Volatility Term Structure | 7 / 7d (Gate Met) | 25 (15B / 10F) | `paper_shadow` |
| **V46** | `crypto-btc-prem-diff5-negative-lag1d-v1` | Crypto Perpetual Derivatives | 8 / 7d (Gate Met) | 99 (50B / 49F) | `paper_shadow` |
| **V48** | `crypto-btc-basis-below-ma10-lag1d-v1` | Crypto Spot-Perp Basis | 7 / 7d (Gate Met) | 93 (47B / 46F) | `paper_shadow` |

## 2. Cross-Strategy Correlation Matrix (Daily Signal Panel)

| Protocol | V16 | V18 | V40 | V42 | V46 | V48 | V8 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **V16** | +1.00 | -0.06 | +0.02 | +0.03 | -0.12 | -0.19 | -0.01 |
| **V18** | -0.06 | +1.00 | +0.40 | +0.10 | +0.05 | +0.17 | +0.28 |
| **V40** | +0.02 | +0.40 | +1.00 | +0.57 | +0.02 | +0.07 | +0.27 |
| **V42** | +0.03 | +0.10 | +0.57 | +1.00 | +0.07 | +0.13 | +0.17 |
| **V46** | -0.12 | +0.05 | +0.02 | +0.07 | +1.00 | +0.41 | -0.09 |
| **V48** | -0.19 | +0.17 | +0.07 | +0.13 | +0.41 | +1.00 | +0.07 |
| **V8** | -0.01 | +0.28 | +0.27 | +0.17 | -0.09 | +0.07 | +1.00 |

## 3. Joint Multi-Strategy Exposure Profile

- **Observation Window**: 2025-02-05 to 2026-08-20 (225 UTC days)
- **Max Concurrent Active Relief Signals**: 6 strategies
- **Mean Active Relief Signals**: 0.95 strategies
- **Max Combined Sizing Multiplier**: 1.2x (assuming 0.20x per candidate)
- **Mean Combined Sizing Multiplier**: 0.19x

### Concurrent Active Signals Distribution (Days)

| Active Strategies Count | Frequency (Days) | Percentage |
| :---: | :---: | :---: |
| **0** | 90 | 40.0% |
| **1** | 86 | 38.2% |
| **2** | 31 | 13.8% |
| **3** | 12 | 5.3% |
| **4** | 2 | 0.9% |
| **5** | 3 | 1.3% |
| **6** | 1 | 0.4% |

## 4. Phase 5 Governance Boundaries

- All strategies remain strictly under `SourcePolicy(dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None)`.
- Live trading and testnet execution remain strictly blocked by the Phase 6 gate.
- The 2026-09..2027-01 future blind dataset remains sealed and unopened.

