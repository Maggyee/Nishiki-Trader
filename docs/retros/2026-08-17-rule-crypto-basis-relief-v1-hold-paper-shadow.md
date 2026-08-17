# 2026-08-17 Rule Crypto Basis Relief v1 Hold Paper Shadow Review

- **Stage**: ADR-007 `paper_shadow`.
- **Source**: `rule_crypto_basis_relief_v1`.
- **Model Version**: `crypto-btc-basis-below-ma10-lag1d-v1`.
- **Decision**: `hold`.
- **Policy**: `SourcePolicy(dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None)`.
- **Rationale**: Passed 2020-2022 development replays (+8.93 USDT base, 21/36 months, 2/3 years) and 2023-2025 independent confirmation (+27.71 USDT base, 20/36 months, 2/3 years, leave-best +18.87 USDT). Candidate is held at paper_shadow for forward dry-run monitoring.
- **Boundaries**:
  - `loads_credentials`: False.
  - `mutates_source_policy`: False.
  - `touches_live_path`: False.
  - `opens_future_blind`: False.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.
