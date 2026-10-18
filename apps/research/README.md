# research

Shared harness for pre-registered research protocols (ADR-014 Gates v2). One
package for every protocol; mechanisms live one module each under
`apps/strategies_freqtrade/research/`.

- **Current phase**: 2 (research). Round 2026-10: v54 trend, v55 order flow.
- **Boundaries**: reads Binance Vision public archives only; writes
  `data/research/` (cache, gitignored) and `docs/research/results/`. Never
  writes `SignalEvent`, never touches `SourcePolicy`, never reads dates from
  2026-09-01 (sealed blind).
- **Next entrypoint**: [docs/research/round-2026-10.md](../../docs/research/round-2026-10.md).

| Module | Content |
|---|---|
| `data.py` | Fetch + SHA256 check against `.CHECKSUM`, manifest, parsers for klines and metrics |
| `replay.py` | Constant-notional replay: costs, episodes, benchmark, drawdown, long-only leg |
| `gates.py` | Circular-shift timing null and Gates v2 checks |
| `protocol.py` | CLI: `fetch <contract>`, `run <contract> --stage development\|confirmation` |

A mechanism module exposes `PRICE_DATASET` and
`target_weights(frames, candidate, params) -> DataFrame` (row t decided after
day t's close, no look-ahead, sum of absolute weights ≤ 1).

```bash
uv run python -m apps.research.protocol fetch docs/research/contracts/v54-trend-vol.json
uv run python -m apps.research.protocol run docs/research/contracts/v54-trend-vol.json --stage development
```
