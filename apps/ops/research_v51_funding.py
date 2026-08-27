"""CLI binding for Research Protocol v51 (BTC funding-rate positioning states).

Provider-corrected recovery of the closed Protocol v50 (see
``apps.ops.research_protocol_v51`` for the frozen contract and the recovery
rationale). The shared pipeline lives in
``apps.ops.research_funding_states``; run ``fetch-dev`` → ``qualify`` →
``develop`` → ``confirm`` in order.
"""

from __future__ import annotations

from apps.ops import research_protocol_v51
from apps.ops.research_funding_states import build_main

main = build_main(research_protocol_v51)

if __name__ == "__main__":
    raise SystemExit(main())
