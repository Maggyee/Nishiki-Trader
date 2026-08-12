# Phase 2 Research Protocol v16

- **Frozen**: 2026-08-12 before opening any Treasury CSV body.
- **Status**: pre-registered; development values unopened.
- **Trading effect**: none.

V16 preserves v15's three economic rules but moves them to direct official
U.S. Treasury annual CSVs and assigns new provider/model fingerprints. The
nominal route supplies 2-year and 10-year yields; the real-yield route supplies
the 10-year real yield. All eight 2019-2022 nominal/real annual URLs returned
HTTP 200 to body-free HEAD qualification.

Rows are normalized by field name and date, sorted, deduplicated, restricted
to the registered window, and inner-joined only where all required values are
numeric. No value is filled. Observations become usable after two calendar
days, which is conservative relative to the Treasury's same-day published
closing curve. Current files are official reconstruction evidence, not a claim
that their HTTP bodies existed unchanged at each historical decision.

The 2020-2022 development reserve and existing performance/evidence gates are
unchanged. The 2023-2025 confirmation may open only after a full development
pass is committed. V15 is not retried; v12-v14, GVZ paper shadow, SourcePolicy,
testnet, live trading, and the shared future blind remain unchanged.
