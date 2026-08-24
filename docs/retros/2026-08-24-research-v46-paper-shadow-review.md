# 2026-08-24 Protocol v46 Paper Shadow Review (Binance Perpetual Premium Index Delta Relief)

- **Date (UTC)**: 2026-08-24T01:45:00Z
- **Operator**: nishiki
- **Strategy**: `rule_crypto_prem_relief_v1`
- **Model Version**: `crypto-btc-prem-diff5-negative-lag1d-v1`
- **Stage**: ADR-007 `paper_shadow`
- **Decision**: `HOLD` (Gate passed, held at `paper_shadow`)

---

## 1. Executive Summary

Protocol v46 evaluates Binance Perpetual Premium Index 5-day delta negative relief on BTCUSDT (`crypto-btc-prem-diff5-negative-lag1d-v1`). The candidate previously passed 2020-2022 development and 2023-2025 independent confirmation (+13.68 USDT base, 2/3 positive years, 21/36 months, 203 positions, leave-best +7.22 USDT).

During the forward paper shadow collection window (2026-08-14 to 2026-08-23), the strategy completed **8 qualified daily runs** (exceeding the target 7-run requirement) with zero drift and full snapshot SHA256 integrity.

---

## 2. Paper Shadow Forward Evidence

- **Collection Period**: 2026-08-14T10:04:05Z to 2026-08-23T04:00:20Z
- **Qualified Runs**: 8 / 7 target runs (`2026-08-14`, `2026-08-17`, `2026-08-18`, `2026-08-19`, `2026-08-20`, `2026-08-21`, `2026-08-22`, `2026-08-23`)
- **Snapshot Integrity**: 8 official point-in-time Binance Vision / API snapshots collected with full SHA256 integrity verification
- **Latest Snapshot SHA256**: `sha256:6f7033180d362b9cc84b6f7ae25c4028c82ffbdc312e60f75637c35ee366219d`
- **Signals Stored**: 99 total `SignalEvent v1` records in SQLite (`data/research-v46/shadow/signals.db`)
  - `buy` signals: 50
  - `flat` signals: 49
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

Protocol v46 has successfully satisfied all forward paper shadow criteria. In accordance with the system design, the candidate remains held at `paper_shadow` under `dry_run=True`. Live trading remains strictly blocked by the Phase 6 gate.
