# ccprophet

**Context Efficiency Advisor for Claude Code** — a local-first auto-optimizer that measures *how well* you use your Claude Code context (not just how much), auto-fixes the waste, and converts the savings into dollars.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-530%20passing-brightgreen)]()
[![Contracts](https://img.shields.io/badge/import--linter-4%2F4%20kept-6E56CF)]()
[![Architecture](https://img.shields.io/badge/arch-clean%20%2B%20hexagonal-6E56CF)]()
[![License](https://img.shields.io/badge/license-MIT-black)]()

**🌐 Language:** **한국어** · [English](#english) · [中文](#中文)

---

## 한국어

### 왜 ccprophet인가?

Claude Code는 강력하지만, 세션이 길어질수록 context가 **조용히 낭비**됩니다. 불필요한 MCP 서버, 무거운 system prompt, 반복 호출되는 tool, 점점 모호해지는 응답 품질 — 누가, 얼마나, 어떤 대가로 이 낭비를 안고 가는지 아무도 모릅니다.

ccprophet은 이 공백을 메웁니다. **완전 로컬** · **zero network** · **단일 DuckDB 파일**.

### 네 문장 약속

| # | 약속 | 의미 |
|---|---|---|
| 1 | **"알려주지 않고, 자동으로 고친다"** | MCP 비활성화 · subset config · `/clear` 추천까지 한 번에 `apply` |
| 2 | **"얼마나 썼나가 아니라, 결과가 더 잘 나왔나"** | 성공 세션의 config·phase 패턴을 학습해 best config를 재현 |
| 3 | **"토큰 수가 아니라, 달러"** | 절약 효과를 월 단위 \$로 환산 |
| 4 | **"Anthropic이 구라 못 치게"** | 동일 모델·옵션에서 품질이 유의미하게 떨어지면 **자동 플래그** |

### 4대 핵심 기능

#### 1. 🔧 Auto Fix (Bloat → Prune → Snapshot → Rollback)
```bash
ccprophet bloat                  # 낭비도 측정
ccprophet recommend              # 근거 포함 개선 제안 (AP-8 Explainable)
ccprophet prune --apply          # settings.json atomic write + SHA256 hash guard
ccprophet snapshot list
ccprophet snapshot restore <id>  # 1-step rollback (AP-7)
```
쓰기 경로: **snapshot 저장 → tmp + os.replace → hash guard → mark_applied**. 동시 편집 감지 시 `SnapshotConflict` 로 안전하게 실패.

#### 2. 🎯 Session Optimizer (Best Config 재현)
```bash
ccprophet mark <id> --outcome success --task-type refactor
ccprophet reproduce refactor --apply       # best config 적용 (snapshot 동일 경로)
ccprophet postmortem <id> --md report.md   # 실패 RCA + Markdown export (FR-11.5)
ccprophet diff <a> <b>
ccprophet subagents
```

#### 3. 💰 Cost Dashboard (토큰 → 달러)
```bash
ccprophet cost --month                     # 월별 \$ + 모델별 내역
ccprophet cost --session <id>              # 세션 단위 비용 + cache hit
ccprophet savings --json                   # Auto Fix 누적 절약액
```
Input · cache_creation · cache_read **분리 과금**. `pricing_rates` 테이블에 rate_id stamp — AP-9 Dollar Transparency.

#### 4. 📊 Quality Watch (다운그레이드 탐지)
```bash
ccprophet quality                          # 최근 30일 trend + z-score 회귀
ccprophet quality --export-parquet out.pq  # 외부 분석 반출
```
7개 지표 (avg_output_tokens, tool_call_success_rate, autocompact_rate, avg_tool_calls, repeat_read_rate, outcome_fail_rate, input_output_ratio) 일별 집계, 기본 2σ 임계치.

### 설치

```bash
uv tool install ccprophet
uv tool install "ccprophet[web,mcp,forecast]"   # Web + MCP + ARIMA

ccprophet install           # hooks · statusLine · DB 초기화
ccprophet doctor --migrate  # 스키마 V1..V5 적용
ccprophet ingest            # 과거 Claude Code JSONL 백필
```
`~/.claude-prophet/events.duckdb` 한 파일, **외부 네트워크 호출 0회**.

### 명령어 요약 (29종)

| 영역 | 명령 |
|---|---|
| Bloat + Auto Fix | `bloat` · `recommend` · `prune` · `snapshot list/restore` |
| Session Optimizer | `mark` · `budget` · `reproduce` · `postmortem` · `diff` · `subagents` |
| Cost | `cost` · `savings` |
| Quality | `quality` |
| Forecast | `forecast` |
| Visual | `serve` (Web DAG + Replay + Compare + Pattern Diff) |
| MCP | `mcp` (read-only stdio) |
| Audit | `claude-md` · `mcp-scan` |
| Ops | `doctor` · `query run/tables/schema` · `rollup` |
| 공통 | `install` · `ingest` · `sessions` · `live` · `statusline` |

모든 분석 명령은 `--json`, Cost-sensitive 명령은 `--cost` 지원.

### 아키텍처

**Clean Architecture + Hexagonal**, `import-linter` 4개 계약으로 CI 강제:
```
harness/ ──▶ adapters/ ──▶ use_cases/ ──▶ ports/ ──▶ domain/
(조립만)     (DuckDB/FastAPI/..)   (Protocol만)     (stdlib 전용)
```
계층 · 테스트 전략 상세: [`docs/LAYERING.md`](docs/LAYERING.md).

### 원칙 (AP-1 ~ AP-9)

| AP | 원칙 |
|---|---|
| AP-1 | Local-First, Zero Network |
| AP-2 | Non-Invasive — 공식 확장점(hooks/JSONL/MCP)만 |
| AP-3 | Silent Fail — hook timeout 10s, 예외는 swallow |
| AP-4 | Single-File Portability |
| AP-5 | Readable Beats Clever — 50~300 LOC/파일 |
| AP-6 | Self-Introspective — MCP와 CLI 1:1 대칭 |
| AP-7 | Reversible Auto-Fix — snapshot → atomic → rollback |
| AP-8 | Explainable — 모든 추천에 rationale 필수 |
| AP-9 | Dollar Transparency — 요율표 + 계산식 공개 |

### 개발

```bash
uv sync --all-extras --dev
uv run pytest -q                     # 530 tests pass
uv run lint-imports                  # 4 contracts KEPT
uv run mypy src/ccprophet            # strict
uv run ruff check src/ tests/
uv run ccprophet serve               # http://127.0.0.1:8765
```
**패키지 매니저는 `uv` 전용** — `pip` 금지 (AGENTS.md §1.4).

### 문서

- [`docs/PRD.md`](docs/PRD.md) v0.6 — 제품 요구사항
- [`docs/ARCHITECT.md`](docs/ARCHITECT.md) v0.4 — 아키텍처
- [`docs/LAYERING.md`](docs/LAYERING.md) v0.3 — 계층 / 테스트
- [`docs/DATAMODELING.md`](docs/DATAMODELING.md) v0.3 — DuckDB 스키마
- [`docs/DESIGN.md`](docs/DESIGN.md) v0.2 — CLI · Web 디자인

### 라이선스

MIT

---

## English

### Why ccprophet?

Claude Code is powerful, but as sessions grow longer, your context is **silently wasted**. Unnecessary MCP servers, heavy system prompts, repeatedly-called tools, response quality that gradually drifts — nobody knows who is paying the cost, or how much.

ccprophet closes this gap. **Fully local** · **zero network** · **single DuckDB file**.

### Four-sentence promise

| # | Promise | What it means |
|---|---|---|
| 1 | **"Don't tell me — fix it"** | Disable MCPs, apply subset config, recommend `/clear` — all in one `apply`. |
| 2 | **"Not how much you used, but whether the result was better"** | Learn config + phase patterns from successful sessions and reproduce the best config. |
| 3 | **"Not token counts — dollars"** | Convert savings into monthly \$. |
| 4 | **"So Anthropic can't quietly downgrade you"** | If quality metrics drop on the same model · same options, **auto-flag it**. |

### The four killer features

#### 1. 🔧 Auto Fix (Bloat → Prune → Snapshot → Rollback)
```bash
ccprophet bloat
ccprophet recommend              # evidence-backed (AP-8 Explainable)
ccprophet prune --apply          # atomic write with SHA-256 hash guard
ccprophet snapshot list
ccprophet snapshot restore <id>  # 1-step rollback (AP-7)
```
Write path: **snapshot → tmp + os.replace → hash guard → mark_applied**. Concurrent edits raise `SnapshotConflict`.

#### 2. 🎯 Session Optimizer (reproduce your best config)
```bash
ccprophet mark <id> --outcome success --task-type refactor
ccprophet reproduce refactor --apply       # applies best config via same snapshot path
ccprophet postmortem <id> --md report.md   # failure RCA + Markdown export (FR-11.5)
ccprophet diff <a> <b>
ccprophet subagents
```

#### 3. 💰 Cost Dashboard (tokens → dollars)
```bash
ccprophet cost --month                     # monthly \$ + per-model
ccprophet cost --session <id>              # per-session cost + cache hit
ccprophet savings --json                   # cumulative Auto Fix savings
```
Input · cache_creation · cache_read are **billed separately**. Every cost output stamps the `pricing_rates.rate_id` used — AP-9 Dollar Transparency.

#### 4. 📊 Quality Watch (downgrade detection)
```bash
ccprophet quality
ccprophet quality --export-parquet out.pq
```
Seven daily metrics aggregated per (model × task_type); z-score guard at 2σ by default. Output carries a 1-line "why" per flag.

### Install

```bash
uv tool install ccprophet
uv tool install "ccprophet[web,mcp,forecast]"

ccprophet install           # hooks · statusLine · DB init
ccprophet doctor --migrate  # apply V1..V5
ccprophet ingest            # backfill past Claude Code JSONL
```
All data lives in one file at `~/.claude-prophet/events.duckdb`. **Zero external network calls.**

### Command catalog (29)

| Area | Commands |
|---|---|
| Bloat + Auto Fix | `bloat` · `recommend` · `prune` · `snapshot list/restore` |
| Session Optimizer | `mark` · `budget` · `reproduce` · `postmortem` · `diff` · `subagents` |
| Cost | `cost` · `savings` |
| Quality | `quality` |
| Forecast | `forecast` |
| Visual | `serve` (DAG + Replay + Compare + Pattern Diff) |
| MCP | `mcp` (read-only stdio) |
| Audit | `claude-md` · `mcp-scan` |
| Ops | `doctor` · `query run/tables/schema` · `rollup` |
| Common | `install` · `ingest` · `sessions` · `live` · `statusline` |

Every analysis command supports `--json`; cost-sensitive commands also accept `--cost`.

### Architecture

**Clean Architecture + Hexagonal**, enforced by 4 import-linter contracts:
```
harness/ ──▶ adapters/ ──▶ use_cases/ ──▶ ports/ ──▶ domain/
(wiring)     (DuckDB/FastAPI/..)   (Protocols only)   (stdlib only)
```
See [`docs/LAYERING.md`](docs/LAYERING.md) for layer rules and test strategy.

### Principles (AP-1 to AP-9)

| AP | Principle |
|---|---|
| AP-1 | Local-First, Zero Network |
| AP-2 | Non-Invasive — only hooks/JSONL/MCP |
| AP-3 | Silent Fail — hook timeout 10s, swallow exceptions |
| AP-4 | Single-File Portability |
| AP-5 | Readable Beats Clever — 50–300 LOC per file |
| AP-6 | Self-Introspective — MCP mirrors CLI 1:1 |
| AP-7 | Reversible Auto-Fix — snapshot → atomic → rollback |
| AP-8 | Explainable — every recommendation carries its *why* |
| AP-9 | Dollar Transparency — rates + formulas public |

### Development

```bash
uv sync --all-extras --dev
uv run pytest -q                     # 530 tests pass
uv run lint-imports                  # 4 contracts KEPT
uv run mypy src/ccprophet            # strict
uv run ruff check src/ tests/
uv run ccprophet serve               # http://127.0.0.1:8765
```
**Package manager is `uv` only — do not use `pip`** (AGENTS.md §1.4).

### Docs

- [`docs/PRD.md`](docs/PRD.md) v0.6 — product requirements
- [`docs/ARCHITECT.md`](docs/ARCHITECT.md) v0.4 — architecture
- [`docs/LAYERING.md`](docs/LAYERING.md) v0.3 — layering & tests
- [`docs/DATAMODELING.md`](docs/DATAMODELING.md) v0.3 — DuckDB schema
- [`docs/DESIGN.md`](docs/DESIGN.md) v0.2 — CLI · Web design

### License

MIT

---

## 中文

### 为什么需要 ccprophet?

Claude Code 很强大,但随着会话变长,上下文会被**悄悄浪费**:没用到的 MCP 服务器、臃肿的 system prompt、反复调用的工具、逐渐飘移的回复质量 —— 没有人知道谁在买单,以及代价是多少。

ccprophet 填补这个空白。**完全本地** · **零网络** · **单一 DuckDB 文件**。

### 四句承诺

| # | 承诺 | 含义 |
|---|---|---|
| 1 | **"不要只告诉我,请自动修复"** | 一条 `apply` 命令完成:禁用 MCP、应用 subset 配置、推荐 `/clear`。 |
| 2 | **"不只看用了多少,更看结果是否变好"** | 学习成功会话的 config 与 phase 模式,在下一次会话中重现最佳配置。 |
| 3 | **"不是 token 数,而是美元"** | 把节省换算成按月的 \$,让投入产出可见。 |
| 4 | **"防止 Anthropic 悄悄降级"** | 同一模型同一参数下,质量指标显著下降则**自动标记**。 |

### 四大核心功能

#### 1. 🔧 Auto Fix (Bloat → Prune → Snapshot → Rollback)
```bash
ccprophet bloat                  # 测量浪费度
ccprophet recommend              # 带依据的改进建议 (AP-8 Explainable)
ccprophet prune --apply          # settings.json 原子写入 + SHA-256 hash guard
ccprophet snapshot list
ccprophet snapshot restore <id>  # 一步回滚 (AP-7)
```
写入路径:**snapshot 保存 → tmp + os.replace → hash guard → mark_applied**。并发编辑时以 `SnapshotConflict` 安全失败。

#### 2. 🎯 Session Optimizer (重现最佳配置)
```bash
ccprophet mark <id> --outcome success --task-type refactor
ccprophet reproduce refactor --apply       # 通过同一 snapshot 路径应用最佳配置
ccprophet postmortem <id> --md report.md   # 失败根因分析 + Markdown 导出 (FR-11.5)
ccprophet diff <a> <b>
ccprophet subagents
```

#### 3. 💰 Cost Dashboard (token → 美元)
```bash
ccprophet cost --month                     # 月度 \$ + 按模型拆分
ccprophet cost --session <id>              # 会话成本 + cache 命中
ccprophet savings --json                   # Auto Fix 累计节省
```
Input · cache_creation · cache_read **分开计费**。每条成本输出都会 stamp 所用的 `pricing_rates.rate_id` —— AP-9 Dollar Transparency。

#### 4. 📊 Quality Watch (降级检测)
```bash
ccprophet quality
ccprophet quality --export-parquet out.pq
```
七个日粒度指标按 (模型 × task_type) 聚合,默认 2σ 回归阈值。每个被标记指标附带一行"为什么"。

### 安装

```bash
uv tool install ccprophet
uv tool install "ccprophet[web,mcp,forecast]"

ccprophet install           # hooks · statusLine · DB 初始化
ccprophet doctor --migrate  # 应用 V1..V5 迁移
ccprophet ingest            # 回填过去的 Claude Code JSONL
```
全部数据存放于 `~/.claude-prophet/events.duckdb` 单文件,**不发起任何外部网络请求**。

### 命令总览 (29 条)

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
| 通用 | `install` · `ingest` · `sessions` · `live` · `statusline` |

所有分析类命令支持 `--json`;与成本相关的命令支持 `--cost`。

### 架构

**Clean Architecture + Hexagonal**,由 4 条 import-linter 契约在 CI 中强制执行:
```
harness/ ──▶ adapters/ ──▶ use_cases/ ──▶ ports/ ──▶ domain/
(仅装配)     (DuckDB/FastAPI/..)   (仅 Protocol)   (仅 stdlib)
```
分层与测试策略详见 [`docs/LAYERING.md`](docs/LAYERING.md)。

### 原则 (AP-1 ~ AP-9)

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

### 开发

```bash
uv sync --all-extras --dev
uv run pytest -q                     # 530 个测试通过
uv run lint-imports                  # 4 条契约 KEPT
uv run mypy src/ccprophet            # strict
uv run ruff check src/ tests/
uv run ccprophet serve               # http://127.0.0.1:8765
```
**包管理只能用 `uv`,禁止使用 `pip`**(见 AGENTS.md §1.4)。

### 文档

- [`docs/PRD.md`](docs/PRD.md) v0.6 — 产品需求
- [`docs/ARCHITECT.md`](docs/ARCHITECT.md) v0.4 — 架构
- [`docs/LAYERING.md`](docs/LAYERING.md) v0.3 — 分层与测试
- [`docs/DATAMODELING.md`](docs/DATAMODELING.md) v0.3 — DuckDB schema
- [`docs/DESIGN.md`](docs/DESIGN.md) v0.2 — CLI · Web 设计

### 许可证

MIT
