# ADR-006：信号源灰度策略与 dry-run

- **状态**：Accepted
- **日期**：2026-05-17
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：消费侧对单一 `(source, model_version)` 的"非全有/全无"风控控制 —— 仓位 haircut、`min_confidence` 覆盖、dry-run（生成意图但不下单）
- **依赖**：
  - ADR-002（`SignalEvent v1` 与策略 / 风控分层）
  - ADR-004 §2.4（重放性：manifest 必须能复现 applied policy）
  - ADR-005 §2.3（灰度概念占位，本 ADR 落地）
- **复审周期**：第一个 `freqai_*` 信号源落地、或第一个 `kind="paper"` 跑通时复审

---

## 1. 背景

ADR-005 §2.3 留了"灰度白名单"概念但没说怎么实施。当前 `Authorization` 只有
`allowed_sources` / `allowed_model_versions` 两个 frozenset，对任何放行的源都是
"全仓上、按 `BaselineStrategyConfig.max_position_pct` 走"。

下一步落地 `freqai_*` 与 `llm_*` 时这会成为致命缺陷：

- 新模型 v0 上线不能直接拿 5% 仓位试，希望先 1% 跑一周；
- LLM agent 输出怀疑度高，希望对它单独抬 `min_confidence` 到 0.7；
- 某个 `model_version` 临时禁用 dry-run 排查，又不想把它从白名单删掉（删掉就丢
  lineage 上下文）。

本 ADR **不**改 `SignalEvent` schema、不引入 tier 名字（"canary"、"gray"
都不进代码），只在 `Authorization` 之上加一张可选的 per-`(source, model_version)`
策略表，以及一个 `dry_run` 决策路径，让消费侧能精细化控制单一源的下单行为，
保留 ADR-002 §4.2 的全局风控（kill-switch）独立运作。

---

## 2. 决策

### 2.1 `SourcePolicy` 数据类

新增 `apps/bridge/validators.py::SourcePolicy`：

```python
@dataclass(frozen=True)
class SourcePolicy:
    position_pct_multiplier: float = 1.0
    min_confidence_override: float | None = None
    dry_run: bool = False
```

字段约束（`__post_init__` 强制）：

- `position_pct_multiplier`：`0.0 ≤ multiplier ≤ 1.0`。乘到 `BaselineSignalStrategy`
  emit 的 `target_position_pct` 上。`0.0` 等价于"接受信号但目标仓位为零"——
  比 `dry_run=True` 弱一档（lineage 记录的目标仓位是 0，没有"would have"价值）。
- `min_confidence_override`：`None`（不改）或 `0.0 ≤ x ≤ 1.0`。比
  `BaselineStrategyConfig.min_confidence` 更严的可覆盖（不允许放宽）—— 即
  `effective = max(config.min_confidence, override)`。这条规则保护策略默认风控
  下限不被 policy 静默调松。
- `dry_run`：`True` 时该 `(source, model_version)` 的所有信号生成 `OrderIntent`
  但消费侧（`BaselineNautilusStrategy`）**不**调 `submit_order`；lineage 仍记录
  "would-have" 的 action / target_position_pct。

`SourcePolicy()` 默认值 = 完全透明（multiplier=1, 无 override, 不 dry-run）。

### 2.2 `Authorization.policies` 字段

```python
@dataclass(frozen=True)
class Authorization:
    allowed_sources: frozenset[str]
    allowed_model_versions: frozenset[str]
    policies: dict[tuple[str, str], SourcePolicy] = field(default_factory=dict)
```

`policies` key 是 `(source, model_version)` tuple；用通配 `"*"` 表示
"该轴上的任何值"。允许的形式：

| key | 含义 |
|---|---|
| `(source, model_version)` | 完全精确匹配 |
| `(source, "*")` | 该 source 任意 model_version 走此策略 |
| `("*", model_version)` | 任意 source 但相同 model_version |
| `("*", "*")` | 全局默认（不推荐，但允许） |

**Lookup 顺序**（精确优先，通配最后；只回退一档）：

```text
1. (source, model_version)
2. (source, "*")
3. ("*", model_version)
4. ("*", "*")
5. SourcePolicy()  # 默认值
```

`Authorization.policy_for(source, model_version) -> SourcePolicy` 是唯一的
查询入口；命中即返回，**不**合并多条 policy（避免出现"两条 partial 叠加"
导致重放性算不准）。

约束：

- `Authorization` 是 `frozen=True` dataclass，`policies` dict 的值在
  `__post_init__` 走完整型校验后可视为只读；本 ADR **不**深冻结
  内部 dict（避免引入 `frozendict` 依赖），但所有使用者必须遵守"只读"
  约定。
- key 中的 `source` 必须满足 ADR-005 §2.1 prefix（或者 `"*"`），否则
  Authorization 拒绝构造；`model_version` 不强制 schema（仍是自由字符串
  或 `"*"`）。

### 2.3 `BaselineSignalStrategy` 应用 policy

```text
1. signal_consumer.evaluate() 走 ADR-002 §4.1 五道闸（schema / venue / auth /
   freshness / confidence）。Authorization 走的是 allowed_sources /
   allowed_model_versions —— policies 在闸里不参与。
2. evaluate() 返回 decision != "accept" → 直接出 OrderIntent(action="skip")，
   不查 policy。
3. evaluate() 返回 "accept" → 调用 self.config.auth.policy_for(event.source,
   event.model_version) 取 policy。
4. 若 policy.min_confidence_override 不是 None，重新跑 confidence 检查：
   effective = max(self.config.min_confidence, policy.min_confidence_override);
   若 event.confidence < effective → OrderIntent(action="skip",
   reason="reject_low_confidence_policy: …")。这是 §2.1 的"只能更严"承诺
   的落地。
5. kill-switch 检查（§4.2 first rule）照常。kill-switch engaged 时即便 dry_run
   policy 在生效，也走 skip 不进 dry_run 路径 —— kill-switch 优先级最高。
6. side → action 映射照常（buy → target_long, sell → target_short, flat →
   target_flat）。
7. target_position_pct = (±max_position_pct or 0) × policy.position_pct_multiplier。
   target_long 仍是正、target_short 仍是负、target_flat 仍是 0。multiplier
   不改符号。
8. 若 policy.dry_run=True → OrderIntent.dry_run = True；action 不变。
```

### 2.4 `OrderIntent.dry_run` 字段

```python
@dataclass(frozen=True)
class OrderIntent:
    signal_id: str
    instrument_id: str
    action: Action
    target_position_pct: float
    reason: str | None = None
    dry_run: bool = False
```

`dry_run=True` 的语义：消费侧**生成意图**但**不发单**。`reason` 不强制带
`dry_run:` 前缀，由消费侧自己判断 `intent.dry_run`，不靠字符串解析。

`Action` 枚举（`target_long / target_short / target_flat / skip`）不变——
dry-run 不是新的 action 类型，而是同一 action 的"演练"标志。这避免了
8 种 action（4×{normal, dry_run}）的组合爆炸。

### 2.5 `BaselineNautilusStrategy._apply_intent` 改

`baseline_nautilus_strategy.py` 的 `_apply_intent` 在 dry_run 分支：

- 不调 `self.submit_order(...)`；
- 不调 `self.close_all_positions(...)`；
- 不返回 client_order_id 列表（返回空 list）；
- lineage 记录 `decision=intent.action`（原值，不带 dry_run 前缀），
  `client_order_ids=[]`；
- runner 可通过 lineage row 是 dry_run 来知道某些 action 没有对应订单
  （参见 §2.6 的 manifest 记录）。

可选改进（**本 ADR 不强制**）：把 `intent.dry_run` 透传到 lineage 的 reason 字段
里作为可读提示，例如 `reason=f"dry_run:{action}"`。是否走这一步留给落地代码
判断；下面 §4 验证标准里允许两种实现。

### 2.6 Runner manifest 记录 applied policies

`backtest_runner._build_manifest` 在 `strategies[0].params` 下加：

```json
"policies": [
  {
    "source": "freqai_lgbm_15m",
    "model_version": "lgbm-2024-01-31",
    "position_pct_multiplier": 0.2,
    "min_confidence_override": 0.7,
    "dry_run": false
  },
  {
    "source": "llm_overnight_review",
    "model_version": "*",
    "position_pct_multiplier": 0.0,
    "min_confidence_override": null,
    "dry_run": true
  }
]
```

策略列表按 `(source, model_version)` 字典序排序，便于 manifest diff。
没有应用任何 policy 时省略该字段（或写成空数组 `[]`，本 ADR 允许两种）。

ADR-004 §2.4 重放性扩展：同 git + 同 signal-store sha + 同 catalog + 同 strategy
params + 同 risk_rules + **同 manifest.strategies[].policies** + 同 Nautilus
版本 → bit-for-bit 相等 `fills.parquet` 与 `stats_pnls`。

---

## 3. 明确不做

- 不为 policy 引入命名层级（"canary"、"gray"、"full"）。multiplier 是数值，
  谁决定 0.05 是"canary" 谁决定 0.2 是"gray"，留给操作员的 PR 描述，不进代码。
- 不允许 policy 改 venue、改 instrument、改 kill-switch 阈值。`SourcePolicy`
  只动 position size、min_confidence、dry-run flag —— 全局 ADR-002 §4.2
  风控不被 policy 覆盖。
- 不让 policy **放宽** `min_confidence`。Override 只能 `>= config.min_confidence`，
  schema 不在数据类强制（不然每次构造都要传 config），由消费侧在 §2.3 第 4
  步用 `max(...)` 在线保护。
- 不允许 SignalEvent 携带 policy（policy 是消费侧决定，不是产生侧）。
  generator 可以**建议** model_version 命名，但 Authorization 拥有最终
  policy 决定权。
- 不在 `apps/bridge/store.py` 加 policy 列。policy 是消费时配置，不持久化在
  `signals` 表里。
- 不在 ADR-006 里规定"何时升级 multiplier"。grad-up 是操作流程，不是 schema。

---

## 4. 验证标准

落地后必须满足：

1. `apps/bridge/validators.py` 含 `SourcePolicy` 数据类、`Authorization.policies`
   字段、`Authorization.policy_for(source, model_version)`。
2. `tests/bridge/test_validators.py` 覆盖：
   - SourcePolicy 默认值 / 范围拒绝（multiplier <0 或 >1，override <0 或 >1）；
   - policy_for 的 4 档 lookup 顺序；
   - policy_for 未命中时返回 SourcePolicy 默认实例（而非 None）。
3. `apps/strategies_nautilus/baseline_strategy.py`：
   - `BaselineSignalStrategy.decide` 使用 policy.multiplier 缩 `target_position_pct`；
   - dry_run policy 让 `OrderIntent.dry_run=True`，action 不变；
   - `min_confidence_override` 被采纳并落到 `reject_low_confidence_policy` 拒绝
     路径（reason 含 effective threshold 数值）；
   - kill-switch 优先级高于 dry_run（先 kill-switch 则不进 dry_run 路径）。
4. `tests/strategies_nautilus/test_baseline_strategy.py` 加最少 6 个新 case
   覆盖以上 4 条规则与边界。
5. `apps/strategies_nautilus/baseline_nautilus_strategy.py::_apply_intent`：
   `intent.dry_run=True` → 不调 submit_order / close_all_positions，返回 `[]`。
6. `tests/strategies_nautilus/test_backtest_reproducibility.py` 或新文件覆盖：
   - dry_run 信号产生 lineage 行但 fills_count 不变；
   - 同 policy 重放两次产生 bit-for-bit 相等的 fills.parquet。
7. `apps/strategies_nautilus/runners/backtest_runner.py::_build_manifest` 把
   applied policies 写入 `manifest.strategies[0].params.policies`。
8. ADR-004 §2.4 重放规则在 `docs/decisions/004-backtest-result-format.md` 不
   需要改文（"strategy params + risk rules 一致" 已经覆盖 policies），但
   `docs/progress/phase-2-signal-source-baselines.md` 后续 dated section 在
   引入第一条 policy 时必须记录使用的 policies。

---

## 5. 后续 ADR

- **ADR-007**：Paper trading runtime（kind="paper" 流程）。Policy 跨 backtest →
  paper → live 时如何升档；本 ADR 的 multiplier 数值在 paper / live 中的
  默认上限。
- **ADR-008**：LLM agent 输出审计 / 双签。LLM 输出的 SourcePolicy 是否必须
  默认 dry_run=True、或必须 multiplier ≤ 0.01，留给本 ADR 决定。

---

**Decided. Phase 2 起 `Authorization` 通过 `policies: dict[(source, model_version), SourcePolicy]` 支持精细化灰度；`SourcePolicy` 控制 position multiplier / `min_confidence_override` / `dry_run`；`OrderIntent.dry_run=True` 在消费侧被识别为"生成意图但不发单"。任何 applied policy 必须出现在 `backtest_runner` 的 `manifest.strategies[0].params.policies`，从而 ADR-004 §2.4 重放性自然扩展覆盖 policy 维度。**
