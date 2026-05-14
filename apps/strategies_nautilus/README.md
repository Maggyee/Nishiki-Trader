# strategies_nautilus

NautilusTrader 上的自定义 Strategy / Actor / 风控扩展。

**当前 Phase**：0（骨架）。代码 Phase 1 开始写。

## 职责

- 订阅 `bridge.SignalEvent`，生成订单意图
- 调用 NautilusTrader `RiskEngine` / `ExecutionEngine`
- 实现 ADR-002 §4.1 策略侧规则（schema / venue / ttl / confidence / source 校验）
- 实现 ADR-002 §4.2 风控侧规则（单日 5% 亏损停机、连续亏损暂停、信号过期拦截）
- 实现 ADR-002 §4.3 降级行为（信号源挂掉 / Redis 挂掉 / 信号格式错误）

## 阶段 1 计划文件

```text
strategies_nautilus/
├── __init__.py
├── signal_consumer.py    # 从 bridge.store 读 SignalEvent
├── baseline_strategy.py  # 最简策略：直接按 SignalEvent.side 开仓
├── risk_rules.py         # 自定义 risk rules（叠加在 nautilus RiskEngine 上）
└── runners/
    └── backtest_runner.py
```

测试：`tests/strategies_nautilus/`

## 边界

- 不直接接交易所 API（用 nautilus 的 binance adapter）
- 不绕过 `RiskEngine`
- 不修改 `nautilus_trader/` 上游源码
- Phase 1–5 都是 backtest / dry-run / testnet；真实账户只在 Phase 6 接入
