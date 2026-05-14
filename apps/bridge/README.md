# bridge

freqtrade / FreqAI → SignalEvent v1 → nautilus 的桥接层。

**当前 Phase**：0（骨架）。代码 Phase 1 开始写。

## 职责

- 定义 `SignalEvent v1` Pydantic 模型（schema 见 `docs/decisions/002-signal-bridge-protocol.md` §3.1）
- 字段验证（§3.2 字段约束）
- SQLite 持久化（§3.3 阶段化传输 / §5 存储和审计）
- `ts_event` 单位转换：ms / μs → ns 整数（§7 测试标准）
- Phase 2 后再加 Redis Stream 通道

## 阶段 1 计划文件

```text
bridge/
├── __init__.py
├── signal_event.py   # Pydantic SignalEvent v1
├── store.py          # SQLite store: write / read / dedupe by signal_id
├── validators.py     # 拒绝过期 / 未授权 source / model_version
└── time_utils.py     # ms / μs / ns 单位转换
```

测试：`tests/bridge/`

## 边界

- 不写 nautilus 策略代码（→ `strategies_nautilus/`）
- 不写 freqtrade 策略代码（→ `strategies_freqtrade/`）
- 不调用真实交易 API（contract §3）
