# strategies_freqtrade

freqtrade / FreqAI 的自定义策略和研究信号 exporter。

- **当前 Phase**：2（研究信号层）。目前没有在用的研究 exporter。v2–v53 的全部
  exporter 已于 2026-10-17 归档（tag `archive/pre-slim-2026-10-17`，
  `apps/strategies_freqtrade/research/`），结论见 `docs/research/README.md`。
- **边界**：只输出 `SignalEvent v1`（`apps/bridge/`），不下单，不接真实订单 API，
  策略代码里不调 LLM。freqtrade 只用于快筛；决定上线的回测在 Nautilus 里跑。
- **下一步入口**：下一个预注册协议（ADR-014 Gates v2）的 exporter 放在
  `research/<mechanism>_signals.py`，一个机制对应一个模块，不按版本复制文件。

## 独立 user_data

`freqtrade/` 是只读的 upstream。我们的 user_data 放在这里，通过 `--userdir` 传给 freqtrade：

```text
apps/strategies_freqtrade/user_data/
├── strategies/      # 自定义 IStrategy
├── freqaimodels/    # FreqAI 模型
├── data/ models/    # gitignored
└── config.json
```

```bash
freqtrade trade --userdir apps/strategies_freqtrade/user_data \
  --config apps/strategies_freqtrade/user_data/config.json
```
