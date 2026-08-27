"""CLI binding for Research Protocol v50 (BTC funding-rate positioning states).

**Protocol v50 is CLOSED at `blocked_provider_qualification`** (2026-08-27):
its frozen development fetch range began at 2019-12, but the Binance Vision
monthly ``fundingRate`` archive for BTCUSDT starts at 2020-01 — the very first
GET returned HTTP 404 before any archive or value was opened. Evidence:
``docs/progress/phase-2-research-v50-provider-qualification.json``. The
unchanged rules were re-registered with a corrected data contract as
Protocol v51 (``apps.ops.research_protocol_v51``), following the v17 → v18
recovery precedent. This binding is retained for the frozen contract's
auditability; do not run it.

The shared pipeline lives in ``apps.ops.research_funding_states``.
"""

from __future__ import annotations

from apps.ops import research_protocol_v50
from apps.ops.research_funding_states import build_main

main = build_main(research_protocol_v50)

if __name__ == "__main__":
    raise SystemExit(main())
