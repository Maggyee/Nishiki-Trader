# Phase 2 Research Protocol v33 Confirmation

- **Status**: pre-registered before COR1Y confirmation value access.
- **Candidate**: unchanged Cboe 1-Year Implied Correlation Relief (`cor1y_relief`).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Future blind**: sealed.
- **Trading effect**: none.

This contract may export confirmation rows only from the already-captured and verified COR1Y snapshot `data/research-v33/raw/cor1y-20260814T013543Z-0cba3dd6341e.json`.
No new network GET is allowed. COR3M and COR6M identities stay rejected.

The rule, lag, costs, catalogs, and gates are unchanged from development.
Confirmation starts flat. A passer becomes eligible only for a separate ADR-007 `paper_shadow` review.
