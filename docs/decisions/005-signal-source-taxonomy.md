# ADR-005：研究层信号源分类与命名

- **状态**：Accepted
- **日期**：2026-05-17
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：`SignalEvent v1.source` / `SignalEvent v1.model_version` 的命名约定、灰度授权语义、新信号源接入流程
- **依赖**：
  - ADR-002（`SignalEvent v1` 是上游研究层进 NautilusTrader 的唯一入口）
  - ADR-004（每次回测必须能反查到信号源）
  - `docs/progress/phase-2-signal-source-baselines.md`（demo / rule 两个 baseline fingerprint）
- **复审周期**：第二个研究信号源家族（freqai 或 llm）落地时复审一次；之后每次新增 source 家族随 ADR 修订

---

## 1. 背景

Phase 2 起 `signals.db` 已经同时承载两种信号源：

- `manual_research` / `binance-fixture-v1`（手动手写 demo）
- `rule_baseline_v1` / `ema5-20+rsi14`（EMA + RSI 规则）

Phase 3 起还要进至少两种：

- `freqai_*`：FreqAI / 经典 ML 训练出来的模型
- `llm_*`：LLM Agent / Prompt-based 研究输出

如果 `source` / `model_version` 字段没有约束，三个月之后 `signals` 表里会出现像 `freqai`、`my-model`、`llm-test-v2`、`agent_v3-experimental` 这种五花八门的命名，
ADR-002 §5 的"信号必须可追踪"和 ADR-004 §2.4 的"重放性"都会被无声地侵蚀：

- 同一个模型在不同的 source 字符串下落库 → 重放时漏过滤；
- 不同模型用同一个 model_version 字符串 → 重放结果混合，对账失败；
- 接入新源时没有自动检查，Authorization 灰度白名单形同虚设。

因此需要一个**强制性的、可机器校验的**信号源分类方案。本 ADR **不**重写 SignalEvent
schema、不引入新存储表、不替换 Authorization 接口；只在现有字段上加约束。

---

## 2. 决策

### 2.1 Source 家族

`SignalEvent.source` 必须匹配以下正则：

```
^(manual|rule|freqai|llm)_[a-z0-9][a-z0-9_]*$
```

即 `<family>_<variant>`：

| family | 含义 | 典型 `source` 例 | 典型 `model_version` 例 |
|---|---|---|---|
| `manual` | 人手填的（fixture、调试、临时 trade idea） | `manual_research`, `manual_morning_review` | `binance-fixture-v1`、自由文本 |
| `rule` | 完全规则化、无 ML 训练；逻辑封装在仓库里 | `rule_baseline_v1`, `rule_ema_rsi`, `rule_breakout_v2` | `<algo>-<key-params>`，例如 `ema5-20+rsi14`、`donchian20-atr14` |
| `freqai` | FreqAI / 经典 ML 模型（LightGBM、XGBoost、CatBoost、stacking 等），有训练产物 | `freqai_lgbm_15m`, `freqai_xgb_4h` | `<algo>-<train-window-end>`，例如 `lgbm-2024-01-31`，或 git short hash `lgbm-a1b2c3d` |
| `llm` | Agent / Prompt-based / 大模型输出 | `llm_overnight_review`, `llm_news_sentiment` | `<model-id>-<prompt-id>`，例如 `claude-opus-4-prompt-v3`、`gpt5-news-v2` |

约束细则：

- variant 部分**只允许小写字母、数字、下划线**；不允许连字符、点、空格。
- variant 必须以字母或数字开头（避免 `manual__` 这种）。
- variant 长度建议 ≤ 32 字符，但本 ADR 不在 schema 层强制（避免与未来 hash-based variant 冲突）。
- 不允许全大写、不允许 `MIXED_case`，统一小写——便于 SQL `LIKE` 和 CLI 引号处理。

### 2.2 `model_version` 命名

`model_version` 仍是自由 UTF-8 字符串（保留 ADR-002 §3.2 原样），**但**强烈推荐按家族走如下约定：

| family | 推荐格式 | 必须传达 |
|---|---|---|
| `manual` | 自由文本 | 可读性、不重复即可 |
| `rule` | `<algo>-<key-params>` | 一眼能复算逻辑；params 包括关键周期、阈值等 |
| `freqai` | `<algo>-<train-window>` 或 `<algo>-<git-short>` | 何时训练、用哪份代码 |
| `llm` | `<model-id>-<prompt-id-or-hash>` | 哪个模型 + 哪个 prompt 版本 |

这一节是**约定**，不在 schema 层校验：ADR-004 §2.4 重放性已经把 model_version 锁进
`run_manifest.signal_source.filter` 和 `signal_id`，违反约定会直接体现在比对失败上。

### 2.3 Authorization 与灰度

`apps.bridge.validators.Authorization` 维持当前结构：

```python
@dataclass(frozen=True)
class Authorization:
    allowed_sources: frozenset[str]
    allowed_model_versions: frozenset[str]
```

灰度（canary）语义本 ADR **只定义概念**、不立即写代码：

- **灰度白名单**：一个 model_version 进 `allowed_model_versions` 后，仍可被消费侧（baseline_strategy / 未来的 risk_rules）按"灰度"对待，例如减半 `max_position_pct`、强制 dry-run、强制更低 `min_confidence`。
- 实施方案由 ADR-006 的 `SourcePolicy` 落地；跨 backtest / paper / live 的升档规则见 ADR-007。
- 现阶段操作建议：新模型先用 `manual_` 或 `rule_` 命名 backtest 验证再升 freqai/llm，避免 Authorization 列表跑前直接对实盘风格的源放行。

### 2.4 新信号源接入流程

每次新增 `<family>_<variant>` 进 `signals.db` 必须：

1. 选定符合 §2.1 的 `source` 与符合 §2.2 的 `model_version`。
2. 把这对加入有效的 `Authorization`（fixture 或 config）。
3. 跑 `backtest_runner` 一次得到一份 ADR-004 bundle。
4. 在 `docs/progress/phase-2-signal-source-baselines.md` 追加一段 dated section 记录 fingerprint（rows / fills / PnL / Win Rate / lineage decisions）；不要覆盖旧 baseline。
5. 把上述四步在同一个 git commit 落地，commit message 注明 `signal-source: <family>_<variant> / <model_version>`。

PR / commit 检查（人工）：

- 没有 ADR-005 §2.1 之外的 family 出现；
- 没有 `source` 不通过 §2.1 正则；
- baseline note 有对应 dated section。

---

## 3. 明确不做

- 不把 source/family 拆成 SignalEvent 单独字段（保持 `source` 是单个 string；family 是 prefix，机器可解析）。
- 不为 source family 建独立表（`signals` 仍是单表，ADR-003 §2 不变）。
- 不在 schema 层强制 `model_version` 格式（只约定，避免束缚未来 hash 或语义版本）。
- 不在 Authorization 引入额外结构（如 `canary_model_versions`）——灰度实施推到后续 ADR。
- 不在 ADR-005 里规定 LLM agent 输出"是否需要双签"——那归 ADR-006（实盘前硬风控）。
- 不重写或迁移历史 `signals.db` 行——现有 `manual_research`、`rule_baseline_v1` 已经合规。

---

## 4. 验证标准

落地后必须满足：

1. `apps/bridge/signal_event.py` 在 `source` 上加 `field_validator`，拒绝不匹配 §2.1 正则的字符串。
2. `tests/bridge/test_signal_event.py`（或新文件）覆盖：
   - 现有合规 `manual_research`、`rule_baseline_v1` 通过；
   - `freqai_lgbm_15m`、`llm_overnight_review` 通过；
   - `unknown_source`、`MANUAL_X`、`manual-research`、`rule_`、`rule_BTC`（大写）等被拒。
3. `apps/strategies_freqtrade/research/baseline_rule_signals.py` 与现有 `signal_consumer` / `baseline_strategy` 全套测试在加约束之后仍然通过（共 fingerprint 不变 → ADR-002 §7 重放保持）。
4. `docs/agent-reading-list.md` "Signal bridge" 行加入 ADR-005 链接。
5. `docs/progress/phase-2-signal-source-baselines.md` 顶部说明 family 字段；旧 fingerprint 不动。

---

## 5. 后续 ADR

- **ADR-006**：实盘前硬风控与灰度实施（包括 Authorization canary 字段、per-source `max_position_pct` 覆盖、强制 dry-run 模式）。
- **Future**：Redis Stream 桥接（与本 ADR 命名无关，但 Redis Stream 的 stream key 应当沿用 `signals.v1.<family>` 的命名，本 ADR 暂留）。
- **ADR-009**：AgentAdvice 审计与 LLM 隔离。任何 `llm_*` 真实落库到
  `signals` 表的实验，仍需另开 LLM SignalEvent 升档 ADR。

---

**Decided. Phase 2 起 `SignalEvent.source` 必须遵循 §2.1 正则；`model_version` 推荐遵循 §2.2 家族约定；新信号源接入必须按 §2.4 流程走，并在 `docs/progress/phase-2-signal-source-baselines.md` 留 fingerprint。**
