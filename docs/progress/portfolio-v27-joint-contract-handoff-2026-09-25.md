# v27 original-byte handoff to the frozen joint contract

Date: 2026-09-25. This offline review replays the retained v27 original report
`data/portfolio-installed-joint-complete-2026-09-25-b.json` (SHA256
`39dc52b389c5812f1bb83bfcf8593bb81567850f2863b469a0a450ba2c57cbdf`)
under the 26 protected sources pinned to commit `3c8a210`. It compares the
fixture budget with the already frozen prospective testnet contract. No venue
request, host installation, credential or scope activation occurs.

Run with `.venv/bin/python -m apps.ops.portfolio_installed_joint_handoff
--joint-complete --report data/portfolio-installed-joint-complete-2026-09-25-b.json
--report-sha256 39dc52b389c5812f1bb83bfcf8593bb81567850f2863b469a0a450ba2c57cbdf`.
The CLI prints a blocked JSON review and can be rerun without consuming a scope.

| Original scenario | Prepared | Accepted | Pending | Result |
| --- | ---: | ---: | ---: | --- |
| `joint_complete_success` | 19 | 19 | none | Complete fixture sequence; unsubscribe acknowledged. |
| `joint_complete_bad_ack` | 19 | 18 | 18 | Foreign unsubscribe acknowledgement refused; no resume. |

The independent replay checks the report hash, protected Git source inventory,
locally imported protected modules, full sequence reports and terminal outcomes.
The four fixture assets are BNB, BTC, ETH (zero), and USDT. Only BNBUSDT and
BTCUSDT depth routes appear. The analogous two-route plan has **15 GETs / 443
documented weight**. The frozen real draft adds one early exchangeInfo GET and
one ETHUSDT depth route: **17 GETs / 468 documented weight**, plus WS/market
operations for **21 durable preparations**. The three-route plan without the
early metadata GET is 16 GETs / 448 weight; that number is not the two-route
fixture budget. Market connection charges and other callers remain unknown.

This replay pins fixture bytes, not a provider-authenticated current source or
a complete enforced shared-egress history. Four fixture assets do not cover the
historical 502-asset account; 496 assets remain outside the three-route pilot
in the [capacity review](portfolio-post-v27-authority-capacity-review-2026-09-25.md).
Real full-account coverage, account stream fence, provider clocks/usage,
independent source authority, gateway capacity and all network/trading admission
remain false. The next boundary is still a prospective authenticated
source/egress evidence adapter with enforced other-caller bounds and fresh
provider evidence, followed by a separately gated testnet review.

Verification: 13 focused tests (including independent original replay, hash
refusal, source-inventory drift and frozen-budget drift), Ruff check and format.
No upstream source or live order path was changed.
