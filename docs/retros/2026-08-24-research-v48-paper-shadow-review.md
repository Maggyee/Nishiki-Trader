# 2026-08-24 Protocol v48 Paper Shadow Review (Binance Perpetual Basis Moving-Average Relief)

- **Date (UTC)**: 2026-08-24T01:45:00Z
- **Operator**: nishiki
- **Strategy**: `rule_crypto_basis_relief_v1`
- **Model Version**: `crypto-btc-basis-below-ma10-lag1d-v1`
- **Stage**: ADR-007 `paper_shadow`
- **Decision**: `HOLD` (Gate passed, held at `paper_shadow`)

---

## 1. Executive Summary

Protocol v48 evaluates Binance Perpetual Basis moving-average relief on BTCUSDT (`crypto-btc-basis-below-ma10-lag1d-v1`). The candidate previously passed 2020-2022 development and 2023-2025 independent confirmation (+27.71 USDT base, 2/3 positive years, 20/36 months, 209 positions, leave-best +18.87 USDT).

During the forward paper shadow collection window (2026-08-17 to 2026-08-23), the strategy successfully completed **7 qualified daily runs** with zero drift and full snapshot SHA256 integrity.

---

## 2. Paper Shadow Forward Evidence

- **Collection Period**: 2026-08-17T08:18:53Z to 2026-08-23T04:15:41Z
- **Qualified Runs**: 7 / 7 target runs (`2026-08-17`, `2026-08-18`, `2026-08-19`, `2026-08-20`, `2026-08-21`, `2026-08-22`, `2026-08-23`)
- **Snapshot Integrity**: 7 official point-in-time Binance Vision / API snapshots collected with full SHA256 integrity verification
- **Latest Snapshot SHA256**: `sha256:bdc3d38395abe55eadb51b16b6be2a7b72575fd5fce3abc804d95390d8ced63b`
- **Signals Stored**: 93 total `SignalEvent v1` records in SQLite (`data/research-v48/shadow/signals.db`)
  - `buy` signals: 47
  - `flat` signals: 46
  - `unauthorized / expired / data gaps`: 0
- **Health Status**: `HEALTHY`

---

## 3. Policy & Boundaries

- **Active Policy**: `SourcePolicy(dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None)`
- **Boundaries**:
  - `loads_credentials`: False
  - `touches_live_path`: False
  - `resumes_testnet`: False
  - `future_blind_opened`: False (2026-09..2027-01 future blind remains sealed)

---

## 4. Verdict & Next Steps

Protocol v48 has successfully satisfied all forward paper shadow criteria. In accordance with the system design, the candidate remains held at `paper_shadow` under `dry_run=True`. Live trading remains strictly blocked by the Phase 6 gate.
