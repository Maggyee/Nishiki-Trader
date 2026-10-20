# Runbook: B2 beta allocation on the Binance Spot testnet

ADR-019 forward test: BTC and ETH held while above their 200-day SMA, at least
four weeks. One runner process per coin; both trade the same testnet account.

## Before the first start

1. Key: Ed25519 pair in `~/.config/trader/` (private key 0600, never printed).
   Register `binance_testnet_ed25519.pub.pem` at testnet.binance.vision, then put
   the issued API key into `~/.config/trader/binance_testnet.env`
   (`BINANCE_TESTNET_API_KEY=`; the secret line is already filled).
2. Daily signals: crontab runs `apps.strategies_freqtrade.beta_signals` at 00:05,
   00:35 and 02:05 UTC; log in `data/beta/signals.log`.
3. Promotion record:
   `docs/retros/2026-10-20-rule-beta-sma200-v1-promote-testnet-canary.md`.
4. `uv run pytest -q` passes and the worktree is clean (the startup guard
   refuses a dirty tree).

## Start (one tmux window per coin)

```bash
tmux new -s beta-btc
set -a; . ~/.config/trader/binance_testnet.env; set +a
mkdir -p data/beta/BTCUSDT
uv run python infra/launchers/beta-sma200-testnet.py BTCUSDT \
  > data/beta/BTCUSDT/runner.stdout.log 2> data/beta/BTCUSDT/runner.stderr.log
# detach with Ctrl-b d; repeat in tmux session beta-eth with ETHUSDT
```

The launcher (gitignored) sets sizing to 0.4 of 5,000 USDT allocated per coin,
scaled by the testnet multiplier 0.2: about 400 USDT per position. It picks up
today's signal at once and rebalances after each Sunday.

## Daily check

- `tail -1 data/beta/signals.log`: yesterday's sides for both coins.
- Newest `data/testnet/<run_id>/logs/alerts.log` for each coin: no
  `kill_switch_fired`, `exchange_error_burst` or `ws_reconnect_burst`.
- Holdings follow the signals: long while the signal is `buy`, flat after `flat`.

## Stop and restart

- Stop: Ctrl-C in the tmux window; the strategy closes its position on stop.
- If a runner died without closing, its position stays on the account and a
  fresh start does not know it. Flatten first with
  `apps.strategies_nautilus.runners.emergency_flatten --kind testnet --run-id <old run>`
  (on the faucet account this may also sell pre-funded balances; acceptable on
  testnet), then start again. Count every such intervention against the 14-day
  no-intervention requirement.
- Testnet resets wipe balances; record the date and restart.
