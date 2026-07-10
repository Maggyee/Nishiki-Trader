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

## 多资产研究信号

`research/multi_asset_rotation_signals.py` 读取对齐的 BTCUSDT/ETHUSDT/SOLUSDT
catalog bars，生成已预注册的月度横截面动量、每日市场宽度或每周 ETH/BTC 相对价值
`SignalEvent v1`。`--start-date/--end-date` 只限制折内决策，之前数据仍可作为不含
前视的 warm-up；`--dry-run` 不写 SignalStore。该 exporter 不计算仓位、不下单，
组合互斥和成本结果由 Nautilus bundles 的被动审查器验证。

`research/flow_positioning_signals.py` 是下一轮预注册 exporter：它从 Binance
Spot 原始 kline 的 quote/taker-buy quote volume 生成周度主动流轮动和 4h 抛售衰竭
信号，并可结合已校验的 USD-M funding archive 生成拥挤度过滤轮动。三者仍只输出
long/flat `SignalEvent v1`，最多选择一个现货资产，不交易期货、不编码仓位或订单。
