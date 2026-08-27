"""CLI binding for Research Protocol v52 (cross-sectional long/short states).

First two-sided, multi-asset protocol (backlog B3). The frozen contract lives
in ``apps.ops.research_protocol_v52``; the shared pipeline in
``apps.ops.research_xs_portfolio``. Run ``fetch-dev`` → ``qualify`` →
``develop`` → ``confirm`` in order; confirmation closes may not be fetched
before a development pass.
"""

from __future__ import annotations

from apps.ops import research_protocol_v52
from apps.ops.research_xs_portfolio import build_main

main = build_main(research_protocol_v52)

if __name__ == "__main__":
    raise SystemExit(main())
