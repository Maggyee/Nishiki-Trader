# 长期开发框架：NautilusTrader 核心量化交易系统

## Summary
基于你的选择，长期路线按“单人长期开发、加密中低频、研究回测优先”设计。核心原则是：`NautilusTrader` 做交易内核，`Freqtrade/FreqAI` 做策略和 ML 研究辅助，多 Agent 做异步研究、复盘和建议，不进入实盘下单热路径。

第一阶段目标不是实盘赚钱，而是建立可重复的数据、回测、评估、复盘闭环。所有策略和 Agent 建议必须先变成结构化信号，再经过 NautilusTrader 回测和硬风控验证。

## Architecture
- 自有代码统一放 `/home/nishiki/projects/trader/apps/`（按 ADR-001 §5 目录结构），不要直接改两个上游仓库。
- 数据层：Binance 历史/实时数据落到 Nautilus `ParquetDataCatalog`；策略元数据、回测结果、Agent 建议先用 SQLite，后期再迁到 Postgres/Timescale。
- 研究层：Freqtrade/FreqAI 用于快速实验特征、模型和策略假设，输出标准化 `SignalEvent`，不直接管理实盘仓位。
- 交易层：NautilusTrader Strategy 读取市场数据和外部信号，生成订单意图；订单必须经过 Nautilus `RiskEngine` 和自定义硬风控后进入 `ExecutionEngine`。
- Agent 层：负责新闻整理、策略解释、回测报告总结、参数建议、异常复盘；只能写入“建议库”，不能直接调用交易 API。
- UI/监控层：先做命令行报告和结构化日志；后期再做 Web 前端展示策略、回测、持仓、风险、Agent 建议和运行状态。

## Public Interfaces
- `SignalEvent`：ML/FreqAI/Agent 统一输出信号。
```json
{
  "symbol": "BTCUSDT",
  "venue": "BINANCE",
  "ts_event": 0,
  "horizon": "15m",
  "side": "buy|sell|flat",
  "score": 0.0,
  "confidence": 0.0,
  "source": "freqai_v1",
  "model_version": "YYYY-MM-DD",
  "ttl_seconds": 900
}
```
- `StrategyCandidate`：Agent 或研究流程提交的策略候选，包含策略名、参数、适用交易对、时间周期、数据范围、风险假设。
- `BacktestResult`：保存收益、回撤、胜率、交易次数、手续费、滑点、样本外表现、失败原因。
- `RiskDecision`：风控输出 `allow|reduce|block`，并记录原因，例如最大回撤、单币种暴露、连续亏损、信号过期。
- `AgentAdvice`：Agent 只能产出建议，字段包括建议类型、依据、置信度、关联回测、是否允许进入候选池。

## Development Roadmap
- Phase 0：项目骨架
  - 建 `apps/`（bridge / strategies_nautilus / strategies_freqtrade / agents / mcp_server / frontend / ops），把数据、策略、回测、ML、Agent、报告分成独立模块。
  - 固定 Python 环境和依赖管理；两个上游仓库只作为源码参考或 editable dependency。
  - 建统一配置：交易对、时间周期、手续费、滑点、数据路径、回测区间。

- Phase 1：数据和回测闭环
  - 接 Binance 历史 K 线，写入 Nautilus `ParquetDataCatalog`。
  - 实现一个最小 Nautilus 策略：只消费 K 线和 `SignalEvent`，不接 Agent。
  - 批量跑回测，输出标准 `BacktestResult`，形成可重复评估流程。

- Phase 2：ML/FreqAI 信号层
  - 用 FreqAI 或自研模型生成预测信号，统一转换成 `SignalEvent`。
  - 建信号有效期、置信度、版本号和回测追踪。
  - 不允许 ML 直接下单，只允许 Nautilus 策略读取信号后决策。

- Phase 3：硬风控和模拟交易
  - 增加最大仓位、最大单笔风险、日亏损限制、连续亏损暂停、信号过期拦截。
  - 接 Binance testnet 或 sandbox，验证订单生命周期、重启恢复、日志完整性。
  - 所有实盘前策略必须通过样本外回测和模拟交易阈值。

- Phase 4：Agent 研究系统
  - 建三个异步 Agent：数据分析 Agent、金融/市场 Agent、复盘 Agent。
  - Agent 读取数据、日志、回测结果和新闻，写入 `AgentAdvice`。
  - Agent 建议必须进入回测队列，不能直接修改实盘策略参数。

- Phase 5：前端和监控
  - 前端展示策略版本、回测曲线、风险状态、持仓、交易日志、Agent 建议。
  - 监控覆盖数据延迟、信号延迟、订单失败、风控拦截、回撤、服务存活。
  - 告警先用日志和本地通知，后期再接 Telegram/邮件/飞书。

- Phase 6：小额实盘
  - 只开放 1-2 个主流交易对，例如 BTC/USDT、ETH/USDT。
  - 初期只允许低杠杆或无杠杆，固定最大资金占用。
  - 实盘参数变更必须来自版本化配置，并保留回滚方案。

## Test Plan
- 数据测试：校验 K 线连续性、重复数据、时区、缺失值、交易对命名。
- 回测测试：同一数据和配置多次运行结果一致；手续费和滑点可配置。
- 信号测试：过期信号、低置信度信号、未知模型版本必须被拒绝或降权。
- 风控测试：超仓位、超亏损、连续亏损、异常价格、重复下单必须被拦截。
- 模拟交易测试：断网、重启、订单未知状态、成交回报延迟后系统能恢复。
- Agent 测试：Agent 输出只能写建议库，不能触发真实交易动作。

## Assumptions
- 初期只做加密货币中低频策略，默认分钟线到小时线，不追求 `<5ms` 实盘决策。
- 单人开发优先低运维复杂度，暂不引入 Kafka、Kubernetes、复杂微服务。
- NautilusTrader 是唯一实盘订单和仓位管理核心；Freqtrade/FreqAI 不直接实盘下单。
- 多 Agent 是研究和复盘辅助，不是自动交易决策者。
- 第一阶段成功标准是“可重复数据 + 可重复回测 + 标准化报告”，不是立即上线实盘。
