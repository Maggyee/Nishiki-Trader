# Upstream Versions

- **Status**: Active
- **Owner**: nishiki
- **Purpose**: Record the upstream source checkouts used for local reference and integration testing.

The root repository does not commit upstream source trees. `freqtrade/` and `nautilus_trader/` are local read-only checkouts, ignored by root git, and updated through a controlled review process.

## freqtrade

- Repository: `https://github.com/freqtrade/freqtrade`
- Local path: `freqtrade/`
- Branch at setup: `develop`
- Commit at setup: `764b32a0cf91cfe04ec53344a4d98e37206c77a3`
- Project role: research, FreqAI experiments, and signal generation reference

## nautilus_trader

- Repository: `https://github.com/nautechsystems/nautilus_trader`
- Local path: `nautilus_trader/`
- Branch at setup: `develop`
- Commit at setup: `2a8953d4a87f75df8cecad07a50c4452f534528b`
- Project role: execution engine, backtesting, risk, portfolio, and exchange adapters

## Update Policy

Do not run `git pull` in upstream checkouts as an unreviewed routine task.

Use this flow:

1. Read upstream release notes or relevant changelog.
2. Fetch the upstream repository.
3. Check out the intended tag, branch, or commit.
4. Run the project regression checks that touch signals, backtests, and Nautilus strategy integration.
5. Update this file with the new commit and reason.
6. Commit the version record update in the root repository.

Production or testnet code should not track unpinned upstream moving targets.
