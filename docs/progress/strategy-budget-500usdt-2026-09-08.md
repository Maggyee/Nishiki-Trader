# 500 USDT planning budget — 2026-09-08

The operator said additional capital was possible and delegated the amount
("按你推荐的金额来吧"). Adopt **500 USDT as a provisional research / future
trial planning budget**, retaining the requested **50% drawdown preference**
and **50 USDT daily loss budget**. The static initial-capital drawdown comparison
is therefore 250 USDT; the daily amount stays 50 USDT, not 50% of capital.
This supersedes the 100 USDT starting-capital input, not the other preferences.

## Reason for the amount

The prior verified six-sleeve raw basket requires 395.66 USDT at daily marks in
the 15 bps stress-cost scenario; 500 leaves approximately 104.34 USDT of sampled
cash headroom. The previously fixed duplicate-normalized diagnostic requires
320.51 USDT in that scenario. Choosing the round 500 USDT planning amount is
budget judgment based on those retained figures, not a fitted strategy or a
guarantee of adequate future capital. It also stays within ADR-001's existing
100–500 USDT initial-live capital bracket, **whose entry gates remain unmet**.

No larger positions, candidate additions, duplicate-exposure allocation choice,
new trades or fee/slippage assumption changes are implied. Only six of ten
candidates have eligible evidence; no full ten-candidate funding claim is made.
Daily marks can miss larger intraday cash requirements and losses. A larger
denominator reduces loss as a fraction of planned initial capital; it does not
improve the strategy's underlying PnL or establish alpha.

## Method and boundary

Reuse the [v2 diagnostic calculation](strategy-followup-method-2026-09-08-v2.md)
with `--capital 500 --max-drawdown 0.5 --daily-loss 50`. The matching JSON retains
schema v2; this note is the updated capital decision. All older methods and
reports remain unchanged. Planned funds are not verified account equity.

**No deposit or live trading is recommended now**: strategy evidence and forward
acceptance remain incomplete. Treat the proposed amount as discretionary capital
whose complete loss would be affordable, not emergency savings or borrowed funds.
Crypto can be highly volatile with substantial total-loss risk; FINRA advises
limiting investment to affordable losses. [FINRA crypto-asset risk guidance](https://www.finra.org/investors/investing/investment-products/crypto-assets/risks)
That general warning does not endorse this project's amount or strategies.

Nautilus runtime settings, SourcePolicy, position sizes, schedules, upstream
source and the live order path remain unchanged. The requested daily research
budget is not silently substituted with an execution-rule reference.

## Evaluation and verification

The unchanged v2 calculation was run with 500 / 0.5 / 50, reading retained
evidence only. At stress costs the raw basket has 104.34 USDT sampled cash
headroom, 100.38 USDT maximum marked drawdown and 27.13 USDT worst sampled daily
loss. The duplicate-normalized diagnostic has 179.49 USDT headroom, 81.56 USDT
drawdown and 22.61 USDT worst sampled daily loss. Both satisfy these static
daily-sampled budget comparisons; neither is thereby approved for trading.

Changed files: this decision and JSON evaluation, `docs/project-status.md`,
`docs/agent-reading-list.md`, the follow-up CLI's completion message and one
regression test in `tests/ops/test_research_strategy_followup.py`. The message
no longer claims funding still fails when the entered budget covers it.
The regression checks that increasing planned capital leaves historical
positions, required cash and the requested daily amount unchanged.
Ruff and the family registry check passed; CLI exit 2 correctly reflects
remaining historical-evidence and forward-acceptance limitations.
Full offline suite: **1,700 passed**, 12 Postgres integration tests deselected
(no dedicated integration DSN supplied). Old report artifacts remain unchanged.
