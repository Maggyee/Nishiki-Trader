# research

Shared harness for pre-registered research protocols (ADR-014 Gates v2). One
package for every protocol; mechanisms live one module each under
`apps/strategies_freqtrade/research/`.

- **Current phase**: 2 (research). Daily rounds 2026-10/10b rejected v54–v59.
  Intraday support (1m klines, 5m metrics, bar-level replay) is built;
  intraday rules are [ADR-018](../../docs/decisions/018-intraday-research.md).
- **Boundaries**: reads Binance Vision public archives only; writes
  `data/research/` (cache, gitignored) and `docs/research/results/`. Never
  writes `SignalEvent`, never touches `SourcePolicy`, never reads dates from
  2026-09-01 (sealed blind).
- **Next entrypoint**: [docs/research/round-2026-10.md](../../docs/research/round-2026-10.md).

| Module | Content |
|---|---|
| `data.py` | Fetch + SHA256 check against `.CHECKSUM`, manifest, parsers for klines (1d, 1m), metrics (daily, 5m) and funding; parsed archives cached as parquet under `data/research/parsed/v{N}/` |
| `replay.py` | Constant-notional replay on any bar: costs, execution lag, funding per settlement, episodes, benchmark, drawdown, long-only leg |
| `gates.py` | Circular-shift timing null (shift by bar or by whole day) and Gates v2 checks |
| `beta.py` | ADR-019 beta admission: compounding equity with units held between rebalances, against buy-and-hold |
| `protocol.py` | CLI: `fetch <contract>`, `run <contract> --stage development\|confirmation` |

A mechanism module exposes `PRICE_DATASET` and
`target_weights(frames, candidate, params) -> DataFrame` (row t decided after
bar t's close, no look-ahead, sum of absolute weights ≤ 1). Rows are bar open
times; a point observation stamped s is usable at row t only if s ≤ t + bar.

Optional contract fields, defaults in brackets: `bar` [`1D`],
`execution_lag_bars` [0], `null.shift_unit` [`bar`, or `day`], and the gate
`active_days_at_least` [absent].

```bash
uv run python -m apps.research.protocol fetch docs/research/contracts/v54-trend-vol.json
uv run python -m apps.research.protocol run docs/research/contracts/v54-trend-vol.json --stage development
```
