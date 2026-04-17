# ccprophet

**Context Efficiency Advisor for Claude Code** — 로컬에서 Claude Code 세션의 낭비(bloat)를 자동으로 없애고, 더 좋은 결과가 나오는 방식을 학습시켜주며, 절약된 토큰을 **달러**로 환산해 보여주는 옵티마이저.

## 네 문장 약속

1. **"알려주는 것"이 아니라 "자동으로 고친다"** — MCP 비활성화, subset config, `/clear` 추천까지 한 번에 apply 가능.
2. **"얼마나 썼나"가 아니라 "결과가 더 잘 나왔나"** — 성공한 세션의 config와 phase 패턴을 학습해 best config를 재현.
3. **"토큰 수"가 아니라 "달러"** — 절약 효과를 월 단위 $로 환산해 의사결정을 쉽게.
4. **"Anthropic이 구라 못 치게"** — 동일 모델·동일 옵션에서 주간/월간 품질 지표가 유의미하게 떨어지면 **자동으로 플래그**.

## 설치

```bash
# 핵심만
uv tool install ccprophet

# Web DAG Viewer · MCP 서버 · ARIMA forecast 포함
uv tool install "ccprophet[web,mcp,forecast]"

# 설치 후 한 번
ccprophet install           # 훅 · statusLine · DB 초기화
ccprophet doctor --migrate  # 스키마 최신화
ccprophet ingest            # 과거 Claude Code JSONL 백필
```

`~/.claude-prophet/events.duckdb` 한 파일로 모든 데이터가 저장됩니다. 완전 로컬, 외부 네트워크 호출 0회.

## 주요 명령 (21개)

| 제품 | 명령 |
|---|---|
| **Bloat + Auto Fix** | `bloat [--cost]` · `recommend` · `prune [--apply]` · `snapshot list/restore` |
| **Session Optimizer** | `mark` · `budget` · `reproduce [--apply]` · `postmortem` · `diff` · `subagents` |
| **Cost Dashboard** | `cost [--month] [--session]` |
| **Quality Watch** | `quality [--export-parquet]` ← *Anthropic 다운그레이드 감지* |
| **Forecasting** | `forecast` (선형 + ARIMA fallback) |
| **Visualization** | `serve` (DAG + Replay + Compare + Pattern Diff) |
| **Introspection** | `mcp` (read-only stdio MCP 서버) |
| **Operations** | `doctor [--migrate] [--repair]` · `query run/tables/schema` · `rollup [--apply]` |
| 공통 | `install [--dry-run]` · `ingest` · `sessions` · `live [--cost]` · `statusline` |

## 아키텍처 요약

Clean Architecture + Hexagonal (Ports & Adapters):

```
harness/  ──▶  adapters/  ──▶  use_cases/  ──▶  ports/  ──▶  domain/
                                                               (stdlib only)
```

- `domain/` — 순수 도메인 (stdlib만, 서드파티 `duckdb`/`fastapi`/`rich` import 금지)
- `use_cases/` — 1파일 = 1유스케이스
- `ports/` — Protocol 인터페이스
- `adapters/` — DuckDB·Rich·FastAPI·Typer·MCP SDK·Statsmodels (각 family 격리)
- `harness/` — 조립만 (비즈니스 로직 금지)

계층 규칙은 `import-linter`가 CI에서 강제합니다.

## 원칙 (PRD AP-*)

| AP | 원칙 |
|---|---|
| AP-1 | Local-First, Zero Network by default |
| AP-2 | Non-Invasive — Claude Code 프로세스 수정 금지 |
| AP-3 | Silent Fail — ccprophet 오류가 Claude Code 세션을 막지 않음 |
| AP-4 | Single-File Portability — DuckDB 한 파일 |
| AP-5 | Readable Beats Clever — 50~300 LOC/파일 |
| AP-6 | Self-Introspective — MCP로 자기 분석 가능 |
| AP-7 | Reversible Auto-Fix — snapshot → atomic write → 1-step rollback |
| AP-8 | Explainable Recommendations — "왜"를 항상 동반 |
| AP-9 | Dollar-Level Transparency — 계산식·요율표 전부 공개 |

## 개발

```bash
uv sync --extra web --extra mcp --extra forecast --dev
uv run pytest -q                                      # 392 tests
uv run --with import-linter lint-imports --config pyproject.toml  # 3 contracts
uv run ccprophet serve                                # http://127.0.0.1:8765
```

## 문서

- `docs/PRD.md` — 제품 요구사항 (무엇을 왜)
- `docs/ARCHITECT.md` — 아키텍처 원칙 · 런타임 구조
- `docs/LAYERING.md` — 계층 규칙 · 테스트 전략
- `docs/DATAMODELING.md` — DuckDB 스키마

## 라이선스

MIT
