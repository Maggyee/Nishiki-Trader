# Phase 2 Research Protocol v34 Confirmation Contract (5Y Treasury Yield Relief / FVX)

- **Status**: pre-registered before FVX confirmation value access.
- **Candidate**: `fvx_relief` (`rule_cboe_fvx_relief_v1 / cboe-fvx-diff5-negative-lag1d-v1`).
- **Development evidence**: committed review `5940fd2` (`development_pass_confirmation_open_eligible`).
- **Confirmation window**: 2023-01-01 through 2025-12-31; unconsumed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Confirmation commitment

Candidate identity, signal definition, parameters (5-obs diff, negative, D+1 lag), execution contract, and cost scenarios are identical to the frozen pre-registration. No parameter tuning, sign flips, or threshold changes are permitted.

The confirmation factor data will be extracted from the qualified snapshot (`data/research-v34/raw/fvx-20260814T014407Z-75b2f82d3153.json`) without any new network requests.
