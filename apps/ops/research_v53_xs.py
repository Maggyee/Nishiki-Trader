"""CLI binding for Research Protocol v53 (cross-sectional momentum re-test).

First protocol frozen under the accepted ADR-014 §11 class-adaptive breadth
gate. Single candidate: the unchanged v52 30d cross-sectional momentum rule
under the new identity ``rule_crypto_xs_momentum_ls_v2 /
crypto-xs-mom30d-top3-bottom3-weekly-v2`` (see the contract's conditional
re-test disclosure). Shared pipeline: ``apps.ops.research_xs_portfolio``.
Run ``fetch-dev`` → ``qualify`` → ``develop`` → ``confirm`` in order; the
2023-2025 confirmation closes may not be fetched before a development pass.
"""

from __future__ import annotations

from apps.ops import research_protocol_v53
from apps.ops.research_xs_portfolio import build_main

main = build_main(research_protocol_v53)

if __name__ == "__main__":
    raise SystemExit(main())
