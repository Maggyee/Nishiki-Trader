# strategies_freqtrade

freqtrade / FreqAI 上的自定义策略和 ML 模型。

**当前 Phase**：2（ML 信号层）。轻量 research exporters 已开始输出
`SignalEvent v1`；完整 freqtrade/FreqAI runtime 仍未接入。

## 约定：使用独立 user_data

freqtrade 默认读 `freqtrade/user_data/`，但 `freqtrade/` 是 upstream 只读。
我们的 user_data 放在这里，通过 `--userdir` 传给 freqtrade：

```text
apps/strategies_freqtrade/
└── user_data/
    ├── strategies/        # 自定义 IStrategy 子类
    ├── freqaimodels/      # FreqAI 预测模型
    ├── data/              # 历史数据缓存（gitignored）
    ├── models/            # 训练产物（gitignored）
    └── config.json        # 运行配置
```

跑：

```bash
freqtrade trade \
  --userdir apps/strategies_freqtrade/user_data \
  --config apps/strategies_freqtrade/user_data/config.json
```

## 边界

- 输出只能写 `signals` 表（SignalEvent v1，见 `apps/bridge/`），**不下单**
- 跑 dry-run 或 producer 模式，**不接真实订单 API**
- 不在策略代码里调 LLM
- backtest 用 freqtrade 快筛；真正决定上线的回测在 nautilus（contract §3）
