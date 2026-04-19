# ccprophet — 中文

**Context Efficiency Advisor for Claude Code** — 本地优先的自动优化器,衡量你使用 Claude Code 上下文的**效率**(不仅仅是用量),自动修复浪费,并把节省换算为美元。

**语言切换** · [한국어](README.ko.md) · [English](README.en.md) · [中文](README.zh.md) · [🏠 root](../README.md)

---

## 为什么需要 ccprophet?

Claude Code 很强大,但随着会话变长,上下文会被**悄悄浪费**:没用到的 MCP 服务器、臃肿的 system prompt、反复调用的工具、逐渐飘移的回复质量 —— 没有人知道谁在买单,以及代价是多少。

ccprophet 填补这个空白。**完全本地** · **零网络** · **单一 DuckDB 文件**。

## 四句承诺

| # | 承诺 | 含义 |
|---|---|---|
| 1 | **"不要只告诉我,请自动修复"** | 一条 `apply` 命令完成:禁用 MCP、应用 subset 配置、推荐 `/clear`。 |
| 2 | **"不只看用了多少,更看结果是否变好"** | 学习成功会话的 config 与 phase 模式,在下一次会话中重现最佳配置。 |
| 3 | **"不是 token 数,而是美元"** | 把节省换算成按月的 \$,让投入产出可见。 |
| 4 | **"逐周质量回归预警"** | 同一模型同一参数下,质量指标显著下降则**自动标记**。对工作负载变化敏感,作为早期信号使用,而非定论。 |

## 四大核心功能

### 1. 🔧 Auto Fix (Bloat → Prune → Snapshot → Rollback)
```bash
ccprophet bloat                  # 测量浪费度
ccprophet recommend              # 带依据的改进建议 (AP-8 Explainable)
ccprophet prune --apply          # settings.json 原子写入 + SHA-256 hash guard
ccprophet snapshot list
ccprophet snapshot restore <id>  # 一步回滚 (AP-7)
```
写入路径:**snapshot 保存 → tmp + os.replace → hash guard → mark_applied**。并发编辑时以 `SnapshotConflict` 安全失败。

### 2. 🎯 Session Optimizer (重现最佳配置)
```bash
ccprophet mark <id> --outcome success --task-type refactor
ccprophet reproduce refactor --apply       # 通过同一 snapshot 路径应用最佳配置
ccprophet postmortem <id> --md report.md   # 失败根因分析 + Markdown 导出 (FR-11.5)
ccprophet diff <a> <b>
ccprophet subagents
```

### 3. 💰 Cost Dashboard (token → 美元)
```bash
ccprophet cost --month                     # 月度 \$ + 按模型拆分
ccprophet cost --session <id>              # 会话成本 + cache 命中
ccprophet savings --json                   # Auto Fix 累计节省
```
Input · cache_creation · cache_read **分开计费**。每条成本输出都会 stamp 所用的 `pricing_rates.rate_id` —— AP-9 Dollar Transparency。

### 4. 📊 Quality Watch (逐周回归预警)
```bash
ccprophet quality
ccprophet quality --export-parquet out.pq
```
七个日粒度指标按 (模型 × task_type) 聚合,默认 2σ 回归阈值。每个被标记指标附带一行"为什么"。指标同时受工作负载影响,请作为早期信号使用,而非定论。

## 安装

```bash
uv tool install ccprophet
uv tool install "ccprophet[web,mcp,forecast]"

ccprophet install           # hooks · statusLine · DB 初始化 + 模式迁移
ccprophet ingest            # 回填过去的 Claude Code JSONL
# 简短别名: `ccp` 同时安装,示例: `ccp bloat`
```
全部数据存放于 `~/.claude-prophet/events.duckdb` 单文件,**不发起任何外部网络请求**。

## 命令总览 (30 条)

| 领域 | 命令 |
|---|---|
| Bloat + Auto Fix | `bloat` · `recommend` · `prune` · `snapshot list/restore` |
| 会话优化 | `mark` · `budget` · `reproduce` · `postmortem` · `diff` · `subagents` |
| 成本 | `cost` · `savings` |
| 质量 | `quality` |
| 预测 | `forecast` |
| 可视化 | `serve` (DAG + Replay + Compare + Pattern Diff) |
| MCP | `mcp` (只读 stdio) |
| 审计 | `claude-md` · `mcp-scan` |
| 运维 | `doctor` · `query run/tables/schema` · `rollup` |
| 通用 | `install` · `uninstall` · `ingest` · `sessions` · `live` · `statusline` |

所有分析类命令支持 `--json`;与成本相关的命令支持 `--cost`。

## 架构

**Clean Architecture + Hexagonal**,由 4 条 import-linter 契约在 CI 中强制执行:
```
harness/ ──▶ adapters/ ──▶ use_cases/ ──▶ ports/ ──▶ domain/
(仅装配)     (DuckDB/FastAPI/..)   (仅 Protocol)   (仅 stdlib)
```
分层与测试策略详见 [`LAYERING.md`](LAYERING.md)。

## 原则 (AP-1 ~ AP-9)

| AP | 原则 |
|---|---|
| AP-1 | 本地优先,零网络 |
| AP-2 | 非侵入式 —— 仅使用官方扩展点 (hooks/JSONL/MCP) |
| AP-3 | 静默失败 —— hook 超时 10s,异常吞掉并日志 |
| AP-4 | 单文件可移植 |
| AP-5 | 可读优于聪明 —— 每文件 50~300 LOC |
| AP-6 | 自我可观测 —— MCP 与 CLI 1:1 对称 |
| AP-7 | 可逆 Auto-Fix —— snapshot → 原子写 → rollback |
| AP-8 | 可解释 —— 每条推荐必带 rationale |
| AP-9 | 美元透明 —— 公开费率表与计算公式 |

## 开发

```bash
uv sync --all-extras --dev
uv run pytest -q                     # 533 个测试通过
uv run lint-imports                  # 4 条契约 KEPT
uv run mypy src/ccprophet            # strict
uv run ruff check src/ tests/
uv run ccprophet serve               # http://127.0.0.1:8765
```
**包管理只能用 `uv`,禁止使用 `pip`**(见 AGENTS.md §1.4)。

## 相关文档

- [`PRD.md`](PRD.md) v0.6 — 产品需求
- [`ARCHITECT.md`](ARCHITECT.md) v0.4 — 架构
- [`LAYERING.md`](LAYERING.md) v0.3 — 分层与测试
- [`DATAMODELING.md`](DATAMODELING.md) v0.3 — DuckDB schema
- [`DESIGN.md`](DESIGN.md) v0.2 — CLI · Web 设计

## 许可证

MIT
