# CLAUDE.md

이 파일은 Claude Code가 `ccprophet` 저장소에서 작업할 때 반드시 참고해야 하는 프로젝트 지침서다. 모든 대화/세션 시작 시 자동 로드된다.

---

## 프로젝트 개요

**ccprophet** — Claude Code의 컨텍스트 **효율성**을 측정하는 로컬 프로파일러. "얼마나 썼나"가 아니라 "얼마나 잘 썼나"를 답한다. 완전 로컬(zero network), DuckDB 기반.

핵심 접점: CLI · Statusline · Web DAG Viewer · MCP Server.

## 1차 참고 문서 (읽기 순서)

새 작업을 시작하기 전에 아래 순서로 관련 문서를 확인한다.

| 문서 | 용도 | 언제 읽는가 |
|---|---|---|
| `docs/PRD.md` | 제품 요구사항 (무엇을 왜) | 기능 추가·범위 판단 |
| `docs/ARCHITECT.md` | 시스템 아키텍처 (어떻게) | 컴포넌트 경계·기술 선택 |
| `docs/DATAMODELING.md` | DuckDB 스키마 | 쿼리·테이블 수정 |
| `docs/LAYERING.md` | **Clean Architecture + Hexagonal** 계층·의존성 방향·테스트 | 새 모듈 추가, 테스트 작성, 리뷰 |
| `docs/DESIGN.md` | 디자인 시스템 (shadcn/ui) | UI/CLI/DAG 렌더링 |
| `AGENTS.md` | 에이전트 작업 규칙 | 커맨드·패키지 관리 (uv 강제) |

충돌 시 우선순위: **PRD > ARCHITECT > LAYERING > DATAMODELING > DESIGN**. 단, 보안·프라이버시 원칙(AP-1, NFR-2/3)과 LAYERING의 의존성 규칙(LP-1, LP-5)은 항상 최상위.

## 아키텍처 원칙 (요약)

상세는 `docs/ARCHITECT.md` §2. 코드 리뷰 기준으로 사용.

- **AP-1**: Local-First, Zero Network by default. 외부 호출 opt-in.
- **AP-2**: Non-Invasive — Claude Code 프로세스 수정 금지, 공식 확장점(hooks/JSONL/OTLP/MCP)만 사용.
- **AP-3**: Silent Fail — ccprophet 오류가 Claude Code 세션을 막으면 안 됨. 훅 timeout 10s는 `settings.json`의 `"timeout": 10`으로 Claude Code가 enforce (ccprophet은 top-level에서 예외를 swallow + 로그).
- **AP-4**: Single-File Portability — DuckDB 단일 파일, HTML 단일 파일, Python 단일 엔트리포인트.
- **AP-5**: Readable Beats Clever — 50~300 LOC/파일 지향.
- **AP-6**: Self-Introspective — MCP 서버로 노출되는 모든 기능은 CLI로도 제공.
- **AP-7**: Reversible Auto-Fix — settings.json 쓰기는 snapshot → atomic write (tmp+rename) → SHA-256 hash guard → 1-step rollback 보장. 모든 쓰기는 `SettingsStore.write_atomic`을 경유한다.
- **AP-8**: Explainable Recommendations — 모든 추천은 "왜"를 동반한다. `Recommendation.rationale` 필드 필수.
- **AP-9**: Dollar Transparency — 토큰 → \$ 환산의 계산식·요율표는 전부 공개. 번들 pricing.toml + 사용자 override + `pricing_rates` 테이블 stamp로 감사 가능.

## 디렉토리 레이아웃 (목표, 계층 구조)

**Clean Architecture + Hexagonal** 기반. 상세 규칙은 `docs/LAYERING.md` §4·§6 참조.

```
ccprophet/
├── pyproject.toml           # uv 기반
├── uv.lock
├── CLAUDE.md · AGENTS.md
├── docs/
│   ├── PRD.md · ARCHITECT.md · DATAMODELING.md
│   ├── LAYERING.md          # 계층·의존성·테스트 전략
│   └── DESIGN.md
├── migrations/              # V{N}__{description}.sql — V1..V5 현재 존재
└── src/ccprophet/
    ├── domain/              # ← 가장 안쪽. third-party import 금지
    │   ├── entities.py      #   Session, Event, ToolCall, Recommendation, Snapshot, ...
    │   ├── values.py        #   SessionId, TokenCount, BloatRatio, Money, ...
    │   ├── errors.py
    │   └── services/        #   BloatCalculator, PhaseDetector, PatternDiff, forecast, ...
    ├── use_cases/           # domain + ports만 import (1 파일 = 1 유스케이스)
    │   ├── ingest_event.py · analyze_bloat.py · detect_phases.py
    │   ├── forecast_compact.py · recommend_action.py · diff_sessions.py
    │   ├── prune_tools.py · apply_pruning.py · restore_snapshot.py · list_snapshots.py
    │   ├── mark_outcome.py · estimate_budget.py · reproduce_session.py · analyze_postmortem.py
    │   ├── compute_session_cost.py · compute_monthly_cost.py · compute_savings.py
    │   ├── assess_quality.py · audit_claude_md.py · rollup_sessions.py
    │   └── list_recommendations.py · list_subagents.py · scan_mcp.py · pattern_diff.py · ...
    ├── ports/               # Protocol 인터페이스. domain만 의존
    │   ├── repositories.py · recommendations.py · snapshots.py · settings.py
    │   ├── subset_profile.py · pricing.py · outcomes.py · subagents.py · session_summary.py
    │   ├── jsonl.py · hot_table_pruner.py · mcp_scan.py
    │   └── clock.py · redactor.py · forecast_model.py · logger.py
    ├── adapters/            # 프레임워크·IO는 여기서만 (family 간 직접 import 금지)
    │   ├── cli/ · web/ · mcp/ · hook/             # driving
    │   ├── persistence/
    │   │   ├── duckdb/      # driven: 실제 DuckDB 구현 (_tz, transaction, migrations, V1/V2/V3/V5 repos, hot_table_pruner)
    │   │   └── inmemory/    # driven: 테스트용 fake (계약 동일)
    │   ├── settings/ · snapshot/ · subset_profile/ · pricing/ · outcome_rules/
    │   ├── redaction/ · clock/ · forecast/ · mcp_scan/
    │   └── filewatch/ · publisher/ · logger/
    ├── harness/             # composition root — 조립만, 로직 금지
    │   ├── cli_main.py · hook_main.py · web_main.py · mcp_main.py
    │   └── commands/        # CLI 명령 분할 (v0.6): _shared / analysis / actions / ops / info / services / …
    └── web/                 # 패키지 내부 static 자산 (index.html, replay.js, pattern_diff.js, vendor/d3.v7.min.js)

tests/
├── unit/{domain,use_cases,adapters}/
├── contract/                # Port 계약 테스트 (Adapter 공통) — 11 계약
├── integration/{adapters/{persistence,cli,web,mcp,hook},use_cases,migrations}/
├── perf/                    # NFR-1 훅 p99<50ms (marker `perf`)
├── property/                # Hypothesis — BloatCalculator·PhaseDetector 불변식
└── fixtures/                # builders, sample JSONL
```

**의존성 방향**: `harness → adapters → {use_cases, ports} → domain`. 반대 방향 import는 `import-linter` 계약으로 CI 차단.

## 개발 명령 (로컬)

**Python 패키지는 `uv`로만 관리한다. `pip` 금지.** (상세 규칙은 `AGENTS.md`)

```bash
# 의존성 설치 / sync
uv sync

# 실행
uv run ccprophet live
uv run ccprophet bloat

# 테스트
uv run pytest

# 타입체크 / 린트
uv run mypy src/ccprophet
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# 새 의존성 추가 (절대 pip install 사용 안 함)
uv add duckdb
uv add --dev pytest

# 새 세션 분석 (dogfooding)
uv run ccprophet ingest
uv run ccprophet bloat --session $(uv run ccprophet sessions --latest --id-only)
```

## 코딩 규칙

### Python

- Python **3.10+**. `from __future__ import annotations` 기본.
- 타입 힌트 필수. `mypy --strict` 통과.
- 포매터·린터: `ruff` (black-compatible, line-length 100).
- Import 그룹: stdlib → third-party → local. `ruff` isort 규칙.
- **계층 import 규칙 (LAYERING.md LP-1/LP-5)**
  - `domain/` · `use_cases/` · `ports/`: stdlib + `dataclasses`·`typing`·`datetime`·`hashlib`·`uuid`만. `duckdb`·`fastapi`·`typer`·`rich`·`watchdog`·`mcp`·`statsmodels`·`httpx`·`requests` **import 금지**.
  - `adapters/<family>/`: 해당 family의 third-party만. **타 family adapter 직접 import 금지** (Port 경유, 필요하면 harness에서 조립).
  - `harness/`: 모두 가능. 단 if/else·for로 비즈니스 로직 분기 금지.
- 훅 수신기(`adapters/hook/receiver.py` + `harness/hook_main.py`)는 **stdlib + duckdb**만 import. rich/typer 금지 (cold start 50ms 목표).
- DuckDB 연결은 `adapters/persistence/duckdb/` 내부에 격리. 쓰기는 Ingestor 경로만, 나머지는 read-only.
- 외부 네트워크 호출이 필요한 신규 코드는 반드시 `CCPROPHET_OFFLINE=1` 환경변수에서 no-op.

### SQL / 스키마

- 신규 테이블·컬럼·인덱스는 `migrations/V{N}__{description}.sql`로 추가하고 `docs/DATAMODELING.md` 동시 업데이트.
- Breaking change는 minor version bump + `ccprophet doctor --migrate`로만 적용.
- 테이블명 snake_case, 컬럼명 snake_case. Timestamp는 UTC.

### 웹 프론트엔드

- `web/` 아래는 **빌드 스텝 없음**. vanilla JS + 동기 `<script>` 로드만.
- React/Vue/TypeScript 도입 금지 (AP-4).
- CSS 변수는 `docs/DESIGN.md` §3의 토큰 이름을 그대로 사용.
- 외부 CDN 호출 금지. 모든 에셋 로컬 번들.

### CLI / Rich

- `--json` 플래그는 모든 분석 커맨드에 필수 (FR-3.2). Cost-sensitive 커맨드 (`bloat`, `live`, `forecast`, `statusline`) 는 `--cost` 지원 (FR-10.3).
- 모든 CLI 메시지는 영어로 작성. i18n (ko/en) 은 Phase 2 로 deferred — 관련 env var (`CCPROF_LOCALE`) 은 v0.6 시점 **구현 안됨**.
- `rich.Theme` 중앙 집중 시스템은 현재 없음. 각 CLI 파일에서 `Console()` + 인라인 색 사용 — Phase 2 에서 `design tokens` 통합 예정.

## 테스트 요구사항

상세 전략은 `docs/LAYERING.md` §7 참조. 요약:

- **계층별 커버리지**: domain ≥95%, use_cases ≥90%, adapters ≥80%, 전체 평균 ≥80% (SM-8).
- **피라미드**: unit 70% / integration 20% / contract 7% / e2e 3%.
- **테스트 더블**: Mock보다 **Fake (InMemory Adapter)** 우선. 모든 Repository Adapter는 `tests/contract/`의 공통 계약 통과 필수.
- **Clock·Redactor·Logger는 Port 주입**. `time.sleep`/`datetime.now()` 직접 호출 금지 (flaky 방지).
- 스키마·쿼리 변경은 `tests/fixtures/sample_session.jsonl`로 회귀 테스트.
- 훅 성능 테스트: `tests/perf/test_hook_latency.py`가 p99 < 50ms 검증 (NFR-1).
- DAG 렌더 회귀: Playwright visual test (50/500/2000 노드).
- Property-based: `BloatCalculator`·`PhaseDetector` 등 도메인 서비스는 Hypothesis로 불변식 검증.
- 의존성 방향 검증: `uv run lint-imports` — Clean Architecture 계층 계약 위반 시 CI 거절.

## 보안·프라이버시

- **기본 redact**: `file_path` → SHA256 hash, `user_prompt.content` → 길이만. 본문 저장은 `config.toml`의 `[redaction]` opt-in 플래그 필요.
- Web Viewer는 **127.0.0.1 bind only**. 0.0.0.0 허용 금지.
- DuckDB 파일 권한은 설치 시 `chmod 600`.
- MCP 서버는 **read-only**. 쓰기 tool 추가 금지.

## 금지 사항 (빠른 참조)

- ❌ `pip install` / `python -m pip` / `python setup.py` — 항상 `uv`.
- ❌ `domain/`·`use_cases/`·`ports/` 에서 `duckdb`·`fastapi`·`typer`·`rich`·`watchdog`·`mcp` import (LAYERING LP-5).
- ❌ Use Case 생성자가 `duckdb.DuckDBPyConnection`·`FastAPI` 등 구체 타입 수신 (Port Protocol만).
- ❌ Adapter A가 Adapter B를 직접 import (Port 경유 또는 harness 조립).
- ❌ Harness에 if/else·for 비즈니스 분기 (조립만).
- ❌ Repository 테스트에서 `Mock` 스텁 (InMemory Fake + Contract 테스트).
- ❌ `time.sleep`·`datetime.now()` 테스트 (Clock Port + FrozenClock).
- ❌ Claude Code 프로세스 래핑·spawn.
- ❌ 외부 네트워크 호출 기본 ON.
- ❌ `0.0.0.0` 바인드.
- ❌ Timeout 없는 훅 실행.
- ❌ MCP tool에 write 기능 추가.
- ❌ Web에 빌드 파이프라인 도입.
- ❌ 다크 모드에 shadow 남용 (DP-1).
- ❌ `docs/`·`DATAMODELING.md`·`LAYERING.md` 업데이트 없이 스키마·계층 변경.

## 커밋·PR

- 커밋 메시지 형식: `<scope>: <summary>` (예: `ingestor: debounce jsonl tail events`).
- PR은 관련 문서 업데이트 포함 (스키마 변경 → DATAMODELING, UI 변경 → DESIGN).
- Breaking schema change는 PR 제목에 `[schema]` 태그.

## 이 파일 수정 규칙

- `CLAUDE.md`·`AGENTS.md`는 **상위 문서 요약·링크**일 뿐이다. 상세 내용은 `docs/*.md`에 두고 여기서는 1~2줄로 참조만.
- 원칙이 바뀌면 `docs/ARCHITECT.md`의 AP-* 또는 `PRD.md`의 NFR-*을 먼저 고치고 여기는 뒤따라 동기화.
