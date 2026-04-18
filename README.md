# ccprophet

**Context Efficiency Advisor for Claude Code** — a local-first auto-optimizer that measures *how well* you use your Claude Code context (not just how much), auto-fixes the waste, and converts the savings into dollars.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-484%20passing-brightgreen)]()
[![Architecture](https://img.shields.io/badge/arch-clean%20%2B%20hexagonal-6E56CF)]()
[![License](https://img.shields.io/badge/license-MIT-black)]()

**🌐 Language:** **한국어** · [English](#english)

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
| 3 | **"토큰 수가 아니라, 달러"** | 절약 효과를 월 단위 \$로 환산. 투입 대비 효과가 보여야 의사결정이 된다 |
| 4 | **"Anthropic이 구라 못 치게"** | 동일 모델·동일 옵션에서 주간/월간 품질 지표가 유의미하게 떨어지면 **자동으로 플래그** |

### 4대 핵심 기능

#### 1. 🔧 Auto Fix (Bloat → Prune → Snapshot → Rollback)
세션별 tool bloat를 계산하고 → 개선안을 **실제로 적용**합니다.

```bash
ccprophet bloat                  # 현재 세션의 낭비도 측정
ccprophet recommend              # 근거 포함 개선 제안 (Explainable)
ccprophet prune --apply          # MCP/tool 비활성화를 settings.json에 atomic write
ccprophet snapshot list          # 적용 이력
ccprophet snapshot restore <id>  # 1-step rollback (AP-7: Reversible)
```

모든 쓰기는 **snapshot → tmp 파일 → os.replace → SHA-256 hash guard** 순. 동시 편집 감지 시 `SnapshotConflict`로 안전하게 실패합니다.

#### 2. 🎯 Session Optimizer (Best Config 재현)
성공한 세션을 `mark`하면, 해당 세션의 config/phase 패턴이 저장되어 **다음 세션에서 `reproduce`로 재현**됩니다.

```bash
ccprophet mark <session-id> --outcome success
ccprophet reproduce <session-id> --apply    # settings.json을 best config로 세팅
ccprophet postmortem <session-id>           # 실패 세션 원인 분석
ccprophet diff <a> <b>                      # 두 세션의 차이를 한 눈에
```

#### 3. 💰 Cost Dashboard (토큰 → 달러)
**AP-9: Dollar-Level Transparency**. 계산식과 요율표를 전부 공개합니다.

```bash
ccprophet cost --month                      # 월별 $ 사용액 + 모델별 내역
ccprophet cost --session <id>               # 세션 단위 비용 + cache hit ratio
ccprophet savings --json                    # Auto Fix로 절약한 총 $ 집계
```

Input · cache_creation · cache_read 각각 분리 과금 — cache 사용률이 높을수록 실제 \$ 이득이 명확하게 나타납니다.

#### 4. 📊 Quality Watch (다운그레이드 탐지)
동일 모델 · 동일 옵션 · 동일 prompt 길이에서 **품질 지표가 유의미하게 떨어지면** z-score 기반으로 플래그합니다.

```bash
ccprophet quality                           # 최근 30일 품질 trend + 회귀 감지
ccprophet quality --export-parquet out.pq   # 외부 분석 도구로 반출
```

### 설치

```bash
# 핵심 기능만
uv tool install ccprophet

# Web DAG Viewer · MCP 서버 · ARIMA forecast 포함
uv tool install "ccprophet[web,mcp,forecast]"

# 설치 후 1회 실행
ccprophet install           # hooks · statusLine · DB 초기화
ccprophet doctor --migrate  # 스키마 최신화
ccprophet ingest            # 과거 Claude Code JSONL 백필 (4.8× 가속)
```

`~/.claude-prophet/events.duckdb` 한 파일에 모든 데이터가 저장됩니다. **외부 네트워크 호출 0회**.

### 명령어 전체 목록

| 영역 | 명령 | 설명 |
|---|---|---|
| **Bloat + Auto Fix** | `bloat [--cost]` | tool/MCP 낭비 측정 |
| | `recommend` | 근거 포함 개선 제안 |
| | `prune [--apply]` | settings.json에 atomic write |
| | `snapshot list` · `snapshot restore <id>` | 이력 조회 · 1-step rollback |
| **Session Optimizer** | `mark <id> --outcome {success\|fail}` | 세션 결과 라벨링 |
| | `budget` | token budget alert |
| | `reproduce <id> [--apply]` | best config 재현 |
| | `postmortem <id>` | 실패 세션 분석 |
| | `diff <a> <b>` | 두 세션 차이 |
| | `subagents` | subagent lifecycle 분석 |
| **Cost Dashboard** | `cost [--month] [--session <id>]` | 토큰 → \$ 환산 |
| | `savings` | Auto Fix 누적 절약액 |
| **Quality Watch** | `quality [--export-parquet]` | 품질 회귀 감지 |
| **Forecasting** | `forecast` | context compact 예측 (linear + ARIMA fallback) |
| **Visualization** | `serve` | http://127.0.0.1:8765 DAG + Replay + Compare |
| **Introspection** | `mcp` | read-only stdio MCP 서버 |
| **Operations** | `doctor [--migrate] [--repair]` | 스키마 검사·복구 |
| | `query run "SQL"` · `query tables` · `query schema` | 로컬 DB 질의 |
| | `rollup [--apply]` | hot-table prune + rollup |
| | `claude-md` | 프로젝트 CLAUDE.md 감사 |
| | `mcp-scan` | 설치된 MCP 서버 스캔 |
| **공통** | `install [--dry-run]` · `ingest` · `sessions` · `live [--cost]` · `statusline` | 공통 유틸 |

모든 분석 명령어는 `--json` 플래그를 지원합니다 (자동화·파이프라인용).

### 아키텍처

**Clean Architecture + Hexagonal (Ports & Adapters)**, import-linter가 CI에서 강제:

```
harness/  ──▶  adapters/  ──▶  use_cases/  ──▶  ports/  ──▶  domain/
(조립만)      (DuckDB/FastAPI/Rich/..)               (Protocol만)     (stdlib 전용)
```

| 디렉터리 | 책임 | 의존성 규칙 |
|---|---|---|
| `domain/` | Entity · Value · 순수 도메인 서비스 | **stdlib 전용** (typing, dataclasses, datetime, hashlib, uuid) |
| `use_cases/` | 1 파일 = 1 유스케이스 | domain + ports만 import |
| `ports/` | Protocol 인터페이스 | domain만 의존 |
| `adapters/` | DuckDB · Rich · FastAPI · Typer · MCP SDK · Statsmodels | family 간 직접 import 금지 (Port 경유) |
| `harness/` | composition root | if/else·for 비즈니스 로직 **금지** |

### 원칙 (AP-1 ~ AP-9)

| AP | 원칙 | 한 줄 설명 |
|---|---|---|
| AP-1 | **Local-First** | `CCPROPHET_OFFLINE=1`에서 완전 동작. 외부 호출 opt-in. |
| AP-2 | **Non-Invasive** | Claude Code 프로세스 수정·래핑 금지. hooks/JSONL/OTLP/MCP만. |
| AP-3 | **Silent Fail** | ccprophet 오류가 Claude Code 세션을 **막지 않는다**. 훅 timeout 10s. |
| AP-4 | **Single-File Portability** | DuckDB 한 파일, HTML 한 파일, Python 한 엔트리포인트. |
| AP-5 | **Readable Beats Clever** | 파일당 50–300 LOC. |
| AP-6 | **Self-Introspective** | MCP로 노출되는 모든 기능은 CLI로도 제공. |
| AP-7 | **Reversible Auto-Fix** | snapshot → atomic write → 1-step rollback 보장. |
| AP-8 | **Explainable** | 모든 추천은 "왜"를 동반한다. |
| AP-9 | **Dollar Transparency** | 계산식과 요율표를 전부 공개. |

### 개발

```bash
uv sync --extra web --extra mcp --extra forecast --dev
uv run pytest -q                                  # 484 tests + 1 skipped
uv run --with import-linter lint-imports          # 3 contracts
uv run mypy src/ccprophet                         # strict
uv run ruff check src/ tests/
uv run ccprophet serve                            # http://127.0.0.1:8765
```

**패키지 관리자는 `uv` 전용입니다. `pip` 사용 금지** (AGENTS.md §1.4).

### 디렉터리 레이아웃

```
ccprophet/
├── pyproject.toml · uv.lock
├── CLAUDE.md · AGENTS.md · README.md
├── docs/PRD.md · ARCHITECT.md · DATAMODELING.md · LAYERING.md · DESIGN.md
├── migrations/V{N}__{description}.sql
└── src/ccprophet/
    ├── domain/{entities,values,errors,services}
    ├── use_cases/
    ├── ports/
    ├── adapters/{cli,web,mcp,hook,persistence/{duckdb,inmemory},...}
    ├── harness/{cli_main,hook_main,web_main,mcp_main,commands/*}
    └── web/{index.html,replay.js,pattern_diff.js,vendor/d3.v7.min.js}
```

### 문서

- [`docs/PRD.md`](docs/PRD.md) — 제품 요구사항 (무엇을 왜)
- [`docs/ARCHITECT.md`](docs/ARCHITECT.md) — 아키텍처 원칙과 런타임 구조
- [`docs/LAYERING.md`](docs/LAYERING.md) — 계층 규칙과 테스트 전략
- [`docs/DATAMODELING.md`](docs/DATAMODELING.md) — DuckDB 스키마
- [`docs/DESIGN.md`](docs/DESIGN.md) — CLI · Web 디자인 시스템

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
| 2 | **"Not how much you used, but whether the result was better"** | Learn config + phase patterns of successful sessions and reproduce the best config. |
| 3 | **"Not token counts — dollars"** | Convert savings into monthly \$. Decisions only happen when ROI is visible. |
| 4 | **"So Anthropic can't quietly downgrade you"** | If weekly/monthly quality metrics drop on the same model + same options, **auto-flag it**. |

### The four killer features

#### 1. 🔧 Auto Fix (Bloat → Prune → Snapshot → Rollback)
Measures tool bloat per session, then **actually applies** the fix.

```bash
ccprophet bloat                  # measure current-session waste
ccprophet recommend              # evidence-backed suggestions (Explainable)
ccprophet prune --apply          # atomic write to settings.json
ccprophet snapshot list          # apply history
ccprophet snapshot restore <id>  # 1-step rollback (AP-7: Reversible)
```

Every write goes through **snapshot → tmp file → os.replace → SHA-256 hash guard**. Concurrent edits are detected and safely abort with `SnapshotConflict`.

#### 2. 🎯 Session Optimizer (reproduce your best config)
`mark` a successful session — its config + phase patterns are stored, then `reproduce` in the next one.

```bash
ccprophet mark <session-id> --outcome success
ccprophet reproduce <session-id> --apply    # apply best config to settings.json
ccprophet postmortem <session-id>           # root-cause analysis for failures
ccprophet diff <a> <b>                      # diff two sessions at a glance
```

#### 3. 💰 Cost Dashboard (tokens → dollars)
**AP-9: Dollar-Level Transparency.** Every formula and rate card is public.

```bash
ccprophet cost --month                      # monthly spend + per-model breakdown
ccprophet cost --session <id>               # per-session cost + cache hit ratio
ccprophet savings --json                    # cumulative \$ saved by Auto Fix
```

Input · cache_creation · cache_read are billed separately — higher cache-hit ratios translate directly into measurable \$ savings.

#### 4. 📊 Quality Watch (downgrade detection)
When quality metrics drop on the same model · same options · same prompt-length distribution, a z-score guard raises a flag.

```bash
ccprophet quality                           # last-30-day trend + regression detection
ccprophet quality --export-parquet out.pq   # export for external analysis
```

### Install

```bash
# core only
uv tool install ccprophet

# with Web DAG Viewer · MCP server · ARIMA forecast
uv tool install "ccprophet[web,mcp,forecast]"

# first-time setup
ccprophet install           # hooks · statusLine · DB init
ccprophet doctor --migrate  # apply schema migrations
ccprophet ingest            # backfill past Claude Code JSONL (4.8× speedup)
```

All data lives in a single file at `~/.claude-prophet/events.duckdb`. **Zero external network calls.**

### Full command reference

| Area | Command | Description |
|---|---|---|
| **Bloat + Auto Fix** | `bloat [--cost]` | measure tool/MCP waste |
| | `recommend` | evidence-backed suggestions |
| | `prune [--apply]` | atomic write to settings.json |
| | `snapshot list` · `snapshot restore <id>` | history · 1-step rollback |
| **Session Optimizer** | `mark <id> --outcome {success\|fail}` | label session outcome |
| | `budget` | token budget alert |
| | `reproduce <id> [--apply]` | reproduce best config |
| | `postmortem <id>` | failure RCA |
| | `diff <a> <b>` | session diff |
| | `subagents` | subagent lifecycle |
| **Cost Dashboard** | `cost [--month] [--session <id>]` | tokens → \$ |
| | `savings` | cumulative Auto Fix savings |
| **Quality Watch** | `quality [--export-parquet]` | regression detection |
| **Forecasting** | `forecast` | context compact prediction (linear + ARIMA fallback) |
| **Visualization** | `serve` | http://127.0.0.1:8765 — DAG + Replay + Compare |
| **Introspection** | `mcp` | read-only stdio MCP server |
| **Operations** | `doctor [--migrate] [--repair]` | schema check/repair |
| | `query run "SQL"` · `query tables` · `query schema` | local DB query |
| | `rollup [--apply]` | hot-table prune + rollup |
| | `claude-md` | audit project `CLAUDE.md` |
| | `mcp-scan` | scan installed MCP servers |
| **Common** | `install [--dry-run]` · `ingest` · `sessions` · `live [--cost]` · `statusline` | utilities |

All analysis commands accept `--json` for pipeline friendliness.

### Architecture

**Clean Architecture + Hexagonal (Ports & Adapters)**, enforced by import-linter in CI:

```
harness/  ──▶  adapters/  ──▶  use_cases/  ──▶  ports/  ──▶  domain/
(wiring)     (DuckDB/FastAPI/Rich/..)             (Protocols only)   (stdlib only)
```

| Directory | Responsibility | Dependency rule |
|---|---|---|
| `domain/` | Entities · Values · pure domain services | **stdlib only** (typing, dataclasses, datetime, hashlib, uuid) |
| `use_cases/` | 1 file = 1 use case | imports domain + ports only |
| `ports/` | Protocol interfaces | depends on domain only |
| `adapters/` | DuckDB · Rich · FastAPI · Typer · MCP SDK · Statsmodels | families must not import each other (go via a Port) |
| `harness/` | composition root | **no** if/else or for-loops on business logic |

### Principles (AP-1 to AP-9)

| AP | Principle | One-line |
|---|---|---|
| AP-1 | **Local-First** | Fully functional under `CCPROPHET_OFFLINE=1`. External calls are opt-in. |
| AP-2 | **Non-Invasive** | No wrapping or patching of Claude Code. Only hooks/JSONL/OTLP/MCP. |
| AP-3 | **Silent Fail** | A ccprophet error must never block the Claude Code session. Hook timeout: 10s. |
| AP-4 | **Single-File Portability** | One DuckDB file, one HTML file, one Python entry point. |
| AP-5 | **Readable Beats Clever** | 50–300 LOC per file. |
| AP-6 | **Self-Introspective** | Everything exposed via MCP is also available via CLI. |
| AP-7 | **Reversible Auto-Fix** | snapshot → atomic write → 1-step rollback, guaranteed. |
| AP-8 | **Explainable** | Every recommendation carries its *why*. |
| AP-9 | **Dollar Transparency** | Every formula and rate card is public. |

### Development

```bash
uv sync --extra web --extra mcp --extra forecast --dev
uv run pytest -q                                  # 484 tests + 1 skipped
uv run --with import-linter lint-imports          # 3 contracts
uv run mypy src/ccprophet                         # strict
uv run ruff check src/ tests/
uv run ccprophet serve                            # http://127.0.0.1:8765
```

**Package manager is `uv` only. Do not use `pip`** (see AGENTS.md §1.4).

### Layout

```
ccprophet/
├── pyproject.toml · uv.lock
├── CLAUDE.md · AGENTS.md · README.md
├── docs/PRD.md · ARCHITECT.md · DATAMODELING.md · LAYERING.md · DESIGN.md
├── migrations/V{N}__{description}.sql
└── src/ccprophet/
    ├── domain/{entities,values,errors,services}
    ├── use_cases/
    ├── ports/
    ├── adapters/{cli,web,mcp,hook,persistence/{duckdb,inmemory},...}
    ├── harness/{cli_main,hook_main,web_main,mcp_main,commands/*}
    └── web/{index.html,replay.js,pattern_diff.js,vendor/d3.v7.min.js}
```

### Docs

- [`docs/PRD.md`](docs/PRD.md) — product requirements (what & why)
- [`docs/ARCHITECT.md`](docs/ARCHITECT.md) — architecture principles and runtime
- [`docs/LAYERING.md`](docs/LAYERING.md) — layering rules and test strategy
- [`docs/DATAMODELING.md`](docs/DATAMODELING.md) — DuckDB schema
- [`docs/DESIGN.md`](docs/DESIGN.md) — CLI · Web design system

### License

MIT
