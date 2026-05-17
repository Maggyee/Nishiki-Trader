# ADR-003：阶段 0/1 项目骨架与目录落地

- **状态**：Accepted
- **日期**：2026-05-14
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：Phase 0/1 项目目录结构、`apps/bridge` 包布局、Phase 1 持久化选型、测试目录约定
- **依赖**：ADR-001 §3.4 / §5 / §6；ADR-002 §3 / §5 / §7；`docs/agent-operating-contract.md` §4 §6
- **复审周期**：Phase 1 完成后复审一次；Phase 2 启动时强制复审

---

## 1. 背景

ADR-001 与 ADR-002 已经分别给出了**技术栈选型**与**信号桥协议**，但落到目录、包、文件、测试的“此时此地”仍有以下不确定项：

1. 哪些目录在 Phase 0/1 必须存在、哪些必须为空。
2. `apps/bridge` 这个 Phase 1 唯一允许写代码的位置，文件应当如何切分。
3. Phase 1 的 `SignalEvent` 用 SQLite 还是 JSONL 落地。
4. 测试目录是否镜像 `apps/`、是否允许跨模块共享 fixture。
5. 简单命名、编码、`__init__.py`、`pyproject.toml` 是否锁死。

这些问题不写下来，每位 agent 接手时都会自由发挥；写下来之后就只需要在评审里贴 ADR-003 §X。

本 ADR 的目的是**用一份决策把上述五个问题钉死**，让 Phase 1 的代码实现不再有“目录怎么放”的讨论。它不重新声明 ADR-001 §5 已经给过的目录结构，也不重新声明 contract §4 已经给过的目录所有权——而是在它们的基础上加一层 Phase 0/1 落地约束。

---

## 2. 决策

### 2.1 Phase 0/1 必须存在的目录

下表只列 Phase 0/1，**不延伸到 Phase 2+**。Phase 2+ 的目录在对应阶段毕业前必须为空（除 `README.md`）。

| 路径 | 状态 | Phase | 说明 |
|---|---|:-:|---|
| `apps/` | 必须存在 | 0 | 项目自有代码根，所有子目录见 `apps/README.md` |
| `apps/bridge/` | 必须存在并在 Phase 1 写代码 | 1 | `SignalEvent v1` 唯一落地位置 |
| `apps/strategies_nautilus/` | 必须存在，骨架占位 | 1（Phase 1 末写最小消费者） | 仅写一个最小 Strategy / Actor，消费 `SignalEvent` |
| `apps/strategies_freqtrade/` | 必须存在，空骨架 | 2 | Phase 0/1 不写代码 |
| `apps/agents/` | 必须存在，空骨架 | 4 | Phase 0/1 不写代码 |
| `apps/mcp_server/` | 必须存在，空骨架 | 4 | Phase 0/1 不写代码 |
| `apps/frontend/` | 必须存在，空骨架 | 5 | Phase 0/1 不写代码 |
| `apps/ops/` | 必须存在 | 1 | 运维脚本、应急平仓占位；Phase 1 至少有一个回放 CLI |
| `infra/` | 必须存在 | 0 | `docker-compose.yml` 在 Phase 0/1 保持 stub |
| `infra/postgres/`、`infra/grafana/`、`infra/n8n/` | 必须存在，空骨架 | 2/4/5 | Phase 0/1 不写配置 |
| `docs/` | 必须存在 | 0 | 见 contract §4 |
| `docs/decisions/` | 必须存在 | 0 | ADR-001/002/003 已落地 |
| `docs/retros/` | 必须存在 | 0 | 每月 retro，`YYYY-MM.md` |
| `notebooks/` | 必须存在，可空 | 0 | 个人研究草稿，文件可 gitignore，目录保留 |
| `data/` | 必须存在 | 0 | 历史数据缓存；目录保留，内容默认 gitignore |
| `tests/` | 必须存在 | 0 | 镜像 `apps/`；Phase 1 末必须覆盖 `bridge/` |
| `freqtrade/`、`nautilus_trader/` | 必须存在 | 0 | 只读 upstream 源码（contract §4） |

**“空骨架”**的最低标准：

- 一个 `README.md` 说明用途、当前 Phase、激活条件、边界。
- 一个 `__init__.py`（仅对 Python 子模块）。
- 不放任何业务代码 / 配置 / 数据。

### 2.2 `apps/bridge` 包布局（Phase 1 锁死）

`apps/bridge/README.md` 已经画出文件清单，本 ADR 把它**升级为决策**，未来新增文件必须先更新本表：

```text
apps/bridge/
├── __init__.py
├── signal_event.py    # SignalEvent v1 Pydantic 模型（ADR-002 §3）
├── time_utils.py      # ms / μs / ns 单位转换 + 校验（ADR-002 §7）
├── validators.py      # 拒绝缺失 / 过期 / 未授权 / 重复（ADR-002 §4.1）
├── store.py           # SQLite 写入 / 去重 / 状态变更（§2.3）
└── cli.py             # 写入 / 校验 / 回放 CLI（ADR-002 §7 可重复回放）
```

包级规则：

- `signal_event.py` 只放 schema，不依赖 `store.py` / `validators.py`。
- `validators.py` 只依赖 `signal_event.py` 和 `time_utils.py`，不依赖 IO。
- `store.py` 是包内唯一允许直接持有 SQLite 连接的位置。
- `cli.py` 通过 `argparse`（不引入 `click`/`typer`）暴露 `bridge write|validate|replay`。
- **不允许**在 `bridge/` 内调用 `nautilus_trader` 或 `freqtrade`；它们只能反向通过 `SignalEvent` 与本包通信。
- **不允许**在 `bridge/` 内调用任何真实交易 API（contract §3）。

### 2.3 Phase 1 持久化：SQLite（含 K 线 Parquet）

**决策**：Phase 1 的 `SignalEvent` 唯一存储是单文件 **SQLite**，路径 `data/bridge/signals.db`。
历史 K 线由 NautilusTrader `ParquetDataCatalog` 接管，路径 `data/catalog/`。两者一致地放在 `data/` 下，整个 `data/` 默认 gitignore（contract §4）。

为什么是 SQLite 而非 JSONL：

- ADR-002 §3.3 / §5 已默认 SQLite，未发现需要偏离的理由。
- `signal_id` 唯一约束 + 状态字段更新（`pending → consumed | rejected | expired`），JSONL 需要重写或追加“状态变更”记录，复杂度更高。
- 回放（ADR-002 §7）需要按 `ts_event` / `source` / `model_version` 索引查询，SQLite 一句 `SELECT` 解决，JSONL 要全量扫。
- 单文件可以原子拷贝、可以 `sqlite3 .dump` 转 SQL 审计，迁移到 Postgres 时（Phase 2）`pgloader` / 手工 `INSERT` 都简单。

Schema 见 ADR-002 §5（`signals` 表）。本 ADR 追加两条约束：

1. SQLite 文件必须开 `PRAGMA journal_mode=WAL`（避免回放进程与写入进程互锁）。
2. 表必须包含 `raw_json TEXT NOT NULL`，原始 JSON 不可变保存（ADR-002 §5）。

**明确放弃**：

- 不在 Phase 1 引入 alembic / 任何 migration 工具——schema 由 `apps/bridge/store.py` 内的 `CREATE TABLE IF NOT EXISTS` 维护，schema 改动随 git 提交。
- 不在 Phase 1 引入 JSONL 双写。Phase 2 切到 Postgres 时再讨论是否额外保留 JSONL 归档。

### 2.4 测试目录布局

`tests/` 镜像 `apps/`（已在 `tests/README.md` 列出）。本 ADR 把它锁死为决策，并加上以下约束：

- 每个 `tests/<module>/` 与 `apps/<module>/` 一一对应。
- 跨模块共享 fixture 放 `tests/conftest.py`；单模块 fixture 放 `tests/<module>/conftest.py`。
- 测试文件命名 `test_<被测文件名>.py`；测试函数 `test_<行为>`。
- 临时 SQLite 必须建在 `tmp_path` 下，不允许污染 `data/`。
- 测试不允许调用真实网络 / 真实交易 API；外部依赖必须 mock。

Phase 1 末必须达到的测试覆盖：见 ADR-002 §7 全部 8 条 + `tests/README.md` 优先级表 high 行。

### 2.5 Python 工程约定

- Python 版本：`>=3.12`（`pyproject.toml` 已锁定）。
- 包管理：`uv`（项目内通过 `uv run` 跑命令；`pyproject.toml` `[dependency-groups].dev` 维护开发依赖）。
- Lint / Format：`ruff`，配置已在 `pyproject.toml`（`E,F,I,W,UP,B,SIM`，行宽 100，忽略 `E501`）。
- 测试：`pytest`，配置已在 `pyproject.toml`（`testpaths=["tests"]`、`pythonpath=["."]`、`--strict-markers`）。
- 不引入：`black`、`isort`、`mypy`、`pylint`、`pre-commit`——ruff 一家全包；类型检查由 IDE / Pydantic 运行时校验承担。
- 所有 Phase 0/1 代码必须能在仓库根直接 `uv run pytest tests/bridge/` 跑通。

### 2.6 README 与 docstring 约定

- 每个项目自有目录必须有 `README.md`，至少包含：用途、当前 Phase、激活条件、边界、下一步入口（CLAUDE.md 项目级要求）。
- 模块顶部不写多段 docstring；函数级只在“为什么”非显而易见时写一行。
- 不在代码里写“这是给 X 用的”、“为 Y issue 加的”这类自参考注释。

### 2.7 Phase 0/1 “毕业”判定

Phase 0/1 视为完成，当且仅当：

1. 本 ADR §2.1 所有“必须存在”的目录已落地，且 Phase 2+ 的目录确实为空骨架。
2. `apps/bridge` 五个文件（§2.2）全部实现，并通过 ADR-002 §7 全部测试。
3. `data/bridge/signals.db` 能由 CLI（§2.2 `bridge write/validate/replay`）写入、校验、回放。
4. `apps/strategies_nautilus/` 存在一个最小消费者：读 SQLite 中的 `SignalEvent`，通过 NautilusTrader Strategy 占位（可只打印决策），不调用真实下单 API。
5. `docs/project-status.md` 已记录 Phase 1 毕业、Phase 2 准入条件。

---

## 3. 明确不做

- 不在 Phase 0/1 引入 Postgres / Redis / TimescaleDB / pgvector。
- 不在 Phase 0/1 引入 Alembic / Atlas / 任何 schema migration 工具。
- 不在 Phase 0/1 引入 FastAPI / Flask / gRPC——`bridge` 只暴露 CLI，不暴露网络服务。
- 不在 Phase 0/1 引入 Docker 化的长驻服务（`infra/docker-compose.yml` 在 Phase 0/1 保持 stub）。
- 不在 `apps/bridge/` 之外写任何 Phase 1 业务逻辑；如果发现需要，先评估是否回到 ADR 修订 §2.2。
- 不为 `apps/agents/`、`apps/mcp_server/`、`apps/frontend/` 写超过 README 的内容。

---

## 4. 验证标准

本 ADR 落地后必须满足：

- 仓库目录与 §2.1 表一致：可由 `find apps infra docs notebooks data tests -maxdepth 2 -type d` 验证。
- `apps/bridge/` 仅包含 §2.2 列出的文件名（或更少），任何新增需更新本 ADR。
- `data/bridge/signals.db` 不被 `git` 跟踪（验证 `.gitignore`）。
- `uv run pytest` 在仓库根可执行（即使 Phase 0 末只有空测试目录）。

如果上述某条不成立，要么修代码使其成立，要么提 ADR 修订。

---

## 5. 后续 ADR

本 ADR 推迟到对应阶段的决策：

- ADR-004：NautilusTrader 回测结果标准格式（Phase 1 末或 Phase 2 初）。
- ADR-005：研究层信号源分类与命名（已落地）。
- ADR-006：信号源灰度策略与 dry-run（已落地）。
- ADR-007：paper trading runtime 与 SourcePolicy 升档（已落地）。
- Future：实盘前硬风控与应急停机规则（Phase 3 前）。
- Future：SQLite → Postgres/TimescaleDB 数据迁移与 schema migration 工具（确认 SQLite 暴露瓶颈之后）。
- Future：Redis Stream 桥接通道（确认 SQLite 桥不够用之后）。

---

**Decided. Phase 0/1 的目录、包布局、持久化、测试约定与“毕业”条件以本 ADR 为准。任何偏离都需先提 ADR 修订。**
