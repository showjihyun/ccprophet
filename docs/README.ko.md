# ccprophet — 한국어

**Context Efficiency Advisor for Claude Code** — Claude Code 세션의 낭비(bloat)를 자동으로 없애고, 더 좋은 결과가 나오는 방식을 학습시켜주며, 절약된 토큰을 **달러**로 환산해 보여주는 로컬 옵티마이저.

**언어 전환** · [한국어](README.ko.md) · [English](README.en.md) · [中文](README.zh.md) · [🏠 root](../README.md)

---

## 왜 ccprophet인가?

Claude Code는 강력하지만, 세션이 길어질수록 context가 **조용히 낭비**됩니다. 불필요한 MCP 서버, 무거운 system prompt, 반복 호출되는 tool, 점점 모호해지는 응답 품질 — 누가, 얼마나, 어떤 대가로 이 낭비를 안고 가는지 아무도 모릅니다.

ccprophet은 이 공백을 메웁니다. **완전 로컬** · **zero network** · **단일 DuckDB 파일**.

## 네 문장 약속

| # | 약속 | 의미 |
|---|---|---|
| 1 | **"알려주지 않고, 자동으로 고친다"** | MCP 비활성화 · subset config · `/clear` 추천까지 한 번에 `apply` |
| 2 | **"얼마나 썼나가 아니라, 결과가 더 잘 나왔나"** | 성공 세션의 config·phase 패턴을 학습해 best config를 재현 |
| 3 | **"토큰 수가 아니라, 달러"** | 절약 효과를 월 단위 \$로 환산 |
| 4 | **"Anthropic이 구라 못 치게"** | 동일 모델·옵션에서 품질이 유의미하게 떨어지면 **자동 플래그** |

## 4대 핵심 기능

### 1. 🔧 Auto Fix (Bloat → Prune → Snapshot → Rollback)
```bash
ccprophet bloat                  # 낭비도 측정
ccprophet recommend              # 근거 포함 개선 제안 (AP-8 Explainable)
ccprophet prune --apply          # settings.json atomic write + SHA256 hash guard
ccprophet snapshot list
ccprophet snapshot restore <id>  # 1-step rollback (AP-7)
```
쓰기 경로: **snapshot 저장 → tmp + os.replace → hash guard → mark_applied**. 동시 편집 감지 시 `SnapshotConflict` 로 안전하게 실패.

### 2. 🎯 Session Optimizer (Best Config 재현)
```bash
ccprophet mark <id> --outcome success --task-type refactor
ccprophet reproduce refactor --apply       # best config 적용 (snapshot 동일 경로)
ccprophet postmortem <id> --md report.md   # 실패 RCA + Markdown export (FR-11.5)
ccprophet diff <a> <b>
ccprophet subagents
```

### 3. 💰 Cost Dashboard (토큰 → 달러)
```bash
ccprophet cost --month                     # 월별 \$ + 모델별 내역
ccprophet cost --session <id>              # 세션 단위 비용 + cache hit
ccprophet savings --json                   # Auto Fix 누적 절약액
```
Input · cache_creation · cache_read **분리 과금**. `pricing_rates` 테이블에 rate_id stamp — AP-9 Dollar Transparency.

### 4. 📊 Quality Watch (다운그레이드 탐지)
```bash
ccprophet quality                          # 최근 30일 trend + z-score 회귀
ccprophet quality --export-parquet out.pq  # 외부 분석 반출
```
7개 지표 (avg_output_tokens, tool_call_success_rate, autocompact_rate, avg_tool_calls, repeat_read_rate, outcome_fail_rate, input_output_ratio) 일별 집계, 기본 2σ 임계치.

## 설치

```bash
uv tool install ccprophet
uv tool install "ccprophet[web,mcp,forecast]"   # Web + MCP + ARIMA

ccprophet install           # hooks · statusLine · DB 초기화
ccprophet doctor --migrate  # 스키마 V1..V5 적용
ccprophet ingest            # 과거 Claude Code JSONL 백필
```
`~/.claude-prophet/events.duckdb` 한 파일, **외부 네트워크 호출 0회**.

## 명령어 요약 (29종)

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

## 아키텍처

**Clean Architecture + Hexagonal**, `import-linter` 4개 계약으로 CI 강제:
```
harness/ ──▶ adapters/ ──▶ use_cases/ ──▶ ports/ ──▶ domain/
(조립만)     (DuckDB/FastAPI/..)   (Protocol만)     (stdlib 전용)
```
계층 · 테스트 전략 상세: [`LAYERING.md`](LAYERING.md).

## 원칙 (AP-1 ~ AP-9)

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

## 개발

```bash
uv sync --all-extras --dev
uv run pytest -q                     # 533 tests pass
uv run lint-imports                  # 4 contracts KEPT
uv run mypy src/ccprophet            # strict
uv run ruff check src/ tests/
uv run ccprophet serve               # http://127.0.0.1:8765
```
**패키지 매니저는 `uv` 전용** — `pip` 금지 (AGENTS.md §1.4).

## 관련 문서

- [`PRD.md`](PRD.md) v0.6 — 제품 요구사항
- [`ARCHITECT.md`](ARCHITECT.md) v0.4 — 아키텍처
- [`LAYERING.md`](LAYERING.md) v0.3 — 계층 / 테스트
- [`DATAMODELING.md`](DATAMODELING.md) v0.3 — DuckDB 스키마
- [`DESIGN.md`](DESIGN.md) v0.2 — CLI · Web 디자인

## 라이선스

MIT
