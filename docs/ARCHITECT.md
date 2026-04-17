# ccprophet — System Architecture

**아키텍처 설계서 (ARCHITECT)**

| 항목 | 내용 |
|---|---|
| 문서 버전 | 0.3 (Sellable MVP Alignment) |
| 작성일 | 2026-04-17 |
| 상위 문서 | `PRD.md` v0.4 |
| 관련 문서 | `LAYERING.md` v0.2 (Clean Architecture + Hexagonal) |
| 대상 독자 | 컨트리뷰터, 연동 파트너, 엔터프라이즈 도입 검토자 |

---

## 1. 문서 목적

본 문서는 `ccprophet`의 시스템 구조, 컴포넌트 경계, 데이터 흐름, 기술 선택 근거, 운영 및 확장 방식을 정의한다. PRD가 "무엇을 왜 만드는가"를 다룬다면, 본 문서는 "어떻게 만들고 어떻게 운영하는가"를 다룬다.

**문서 분업**
- `PRD.md` — 제품 요구사항·기능 목록 (WHAT/WHY)
- 본 문서 — 런타임 컴포넌트·통합·배포·운영 (HOW at runtime)
- `LAYERING.md` — **Clean Architecture + Hexagonal Ports/Adapters** 기반 계층·의존성 방향·테스트 설계 (HOW at code level). **본 문서의 §3–§4를 계층 관점으로 재해석한 권위 문서.**
- `DATAMODELING.md` — DuckDB 스키마·쿼리 (HOW at data level)
- `DESIGN.md` — UI/CLI/Web 시각 언어

본 문서의 §3에 나오는 "Ingestor / Storage / Analyzer / Viewer / MCP" 5+1 구조는 **런타임 배치** 관점이고, `LAYERING.md`의 "Domain / Use Cases / Ports / Adapters / Harness"는 **코드 계층** 관점이다. 둘은 같은 시스템을 두 축으로 본 것이며, 매핑은 §4.0에서 정리한다.

## 2. 아키텍처 원칙 (Architecture Principles)

이 **9가지** 원칙은 모든 설계 의사결정의 상위 기준이 된다. 트레이드오프가 발생하면 원칙 순서에 따른다. AP-1~6은 "관측·로컬성", AP-7~9는 v0.4에서 추가된 "액션·안전·투명성" 축이다.

**AP-1. Local-First, Zero Network by Default**
외부 네트워크 호출·클라우드 동기화·원격 저장소는 기본값이 OFF. opt-in으로만 활성화. 공공기관·금융·망분리 환경에서 그대로 동작해야 한다.

**AP-2. Non-Invasive to Claude Code**
Claude Code 프로세스를 수정하거나 래핑하지 않는다. Anthropic이 공식적으로 제공하는 확장점 (hooks, JSONL, OTLP, MCP)만 사용한다. 업스트림 변경에 취약해지지 않기 위함.

**AP-3. Silent Fail, Never Block**
ccprophet의 어떤 실패도 Claude Code 세션을 방해하지 않는다. 훅 타임아웃 10초, 예외는 로그만 남기고 삼킨다.

**AP-4. Single-File Portability**
DuckDB 단일 파일, HTML 단일 파일, Python 단일 엔트리포인트. `scp` 한 번으로 분석 환경 이관 가능해야 한다.

**AP-5. Readable Beats Clever**
컴포넌트는 50~300 LOC 범위를 지향. 숨겨진 추상화보다 명시적 데이터 플로우.

**AP-6. Self-Introspective**
ccprophet 자신이 Claude Code 세션의 분석 대상이 될 수 있어야 한다. 즉 MCP 서버로 노출되는 모든 기능은 CLI로도 동일하게 제공된다.

**AP-7. Reversible Auto-Fix**
ccprophet이 사용자 파일(`.claude/settings.json`, `.mcp.json` 등)을 **자동으로 수정**하는 경로는 반드시 (1) 직전 스냅샷 기록, (2) 원자적 write(`tmp + rename`), (3) `snapshot restore`로 1-step 원복 가능해야 한다. 스냅샷 없이 apply 금지. MCP 서버는 쓰기 경로를 갖지 않는다.

**AP-8. Explainable Recommendations**
모든 추천·예측은 **"왜"**를 1줄 이상으로 수반해야 한다. "최근 30일 0회 사용", "유사 세션 7건 평균", "성공 라벨 5건 공통 패턴" 등 근거·샘플수·confidence를 사용자에게 그대로 노출한다. 블랙박스 금지.

**AP-9. Dollar-Level Transparency**
Cost 계산식·요율표는 전부 공개, 오프라인 계산, 사용자 override 가능. "예상" 절감과 "실측" 절감은 항상 다른 라벨로 표시한다. 네트워크 기반 실시간 요율 조회 금지.

## 3. 시스템 전체 구조 (System Overview)

v0.4에서는 "관측 → 분석" 파이프라인 끝에 **Auto-Fix / Outcome / Cost 계층**을 추가한다. 읽기 레이어 셋 (CLI/Web/MCP)이 여전히 접점이지만, 그 뒤로 **분석 커널(Analysis Kernel)** 이 두 개 트랙으로 나뉜다: "상태를 본다" (bloat/phase/forecast)와 "상태를 바꾼다" (recommend/prune/apply/reproduce).

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Claude Code Runtime                             │
│   [User Terminal]──►[Claude Code]──►[Anthropic API]                 │
│                         │    writes JSONL                           │
│                         │    fires hooks                            │
│                         └──  reads .claude/settings.json            │
└─────────────────────────┼───────────────────────────────────────────┘
                          │                       ▲
                   (ingest paths)         (Auto-Fix patch paths, AP-7)
                          ▼                       │
┌─────────────────────────────────────────────────┴───────────────────┐
│                     ccprophet Boundary                              │
│                                                                     │
│  ┌─────────────────┐   ┌───────────────────────────────────────┐    │
│  │ Ingestor Layer  │   │        Storage Layer (DuckDB)         │    │
│  │ hook_receiver   │──►│  events · sessions · tool_calls ·     │    │
│  │ jsonl_tailer    │──►│  phases · recommendations · snapshots │    │
│  │ otlp_bridge     │──►│  outcome_labels · pricing_rates       │    │
│  └─────────────────┘   └────────┬──────────────────────────────┘    │
│                                 │ read-only (from viewers)          │
│                                 │ write (from Ingestor + Auto-Fix)  │
│   ┌───────────────────┬─────────┴────────┬──────────────────┐       │
│   ▼                   ▼                  ▼                  ▼       │
│ ┌────────────┐ ┌────────────────┐ ┌──────────────┐ ┌──────────────┐ │
│ │  Analysis  │ │   Auto-Fix     │ │   Outcome    │ │     Cost     │ │
│ │   Kernel   │ │   Kernel       │ │   Engine     │ │   Kernel     │ │
│ │            │ │                │ │              │ │              │ │
│ │ Bloat      │ │ Recommender    │ │ Clusterer    │ │ PricingProv. │ │
│ │ PhaseDet.  │ │ SettingsPatch. │ │ OutcomeClass │ │ CostCalc.    │ │
│ │ Forecaster │ │ SnapshotStore  │ │ Postmortem   │ │ SavingsCalc  │ │
│ └──────┬─────┘ └────────┬───────┘ └──────┬───────┘ └──────┬───────┘ │
│        │                │                │                │         │
│        └──────┬─────────┴────────┬───────┴────────┬───────┘         │
│               ▼                  ▼                ▼                 │
│      ┌──────────────┐   ┌──────────────┐   ┌──────────────┐         │
│      │ Analyzer CLI │   │  Web Viewer  │   │  MCP Server  │         │
│      │              │   │ (replay+DAG) │   │ (read-only)  │         │
│      └──────┬───────┘   └──────┬───────┘   └──────┬───────┘         │
│             │                  │                  │                 │
└─────────────┼──────────────────┼──────────────────┼─────────────────┘
              ▼                  ▼                  ▼
       Terminal / statusline  localhost:8765  Claude Code self-query
                              (browser)
```

시스템은 **Ingestor → Storage → (Analysis / Auto-Fix / Outcome / Cost) 4 Kernels → (CLI / Web / MCP) 3 Adapters** 구조다. Storage를 중심으로 쓰기 경로는 두 가지로 구분된다: (A) 이벤트 적재(Ingestor), (B) 자동 변경 기록(Auto-Fix Kernel의 SnapshotStore). Auto-Fix Kernel만이 `.claude/settings.json`·`.mcp.json`을 수정할 수 있으며, 반드시 SnapshotStore를 선행시킨다 (AP-7).

## 4. 컴포넌트 상세 (Components)

### 4.0 레이어 관점과의 매핑

§4의 각 컴포넌트는 `LAYERING.md`의 Clean+Hexagonal 계층으로 다음과 같이 분해된다.

| 본 문서의 런타임 컴포넌트 | LAYERING.md 계층 배치 |
|---|---|
| `hook_receiver.py` | **Driving Adapter** (`adapters/hook/`) + `harness/hook_main.py` |
| `jsonl_tailer.py` | **Driven Adapter** (`adapters/filewatch/`) + **Driving Adapter**로 `BackfillFromJsonlUseCase` 호출 |
| `otlp_bridge.py` | **Driving Adapter** (`adapters/otlp/`, opt-in) |
| Storage (DuckDB) | **Driven Adapter** (`adapters/persistence/duckdb/*`) — `EventRepository`·`SessionRepository`·`RecommendationRepository`·`SnapshotRepository`·`OutcomeRepository`·`PricingRateRepository` 등 구현 |
| Analyzer CLI | **Driving Adapter** (`adapters/cli/`) + `harness/cli_main.py` |
| Web Viewer | **Driving Adapter** (`adapters/web/`) + `harness/web_main.py` |
| MCP Server | **Driving Adapter** (`adapters/mcp/`) + `harness/mcp_main.py` (read-only) |
| Forecaster kernel | **Domain Service** (`domain/services/forecast.py`) + **Driven Port** `ForecastModel` + 교체 가능한 **Driven Adapter** 2종 (`adapters/forecast/{linear,arima}.py`) |
| **Recommender** | **Domain Service** (`domain/services/recommender.py`) — rule 엔진은 도메인에, confidence·근거 생성 포함 |
| **SettingsPatcher** | **Driven Port** `SettingsStore` + **Adapter** `adapters/settings/jsonfile.py` — atomic tmp+rename write |
| **SnapshotStore** | **Driven Port** `SnapshotStore` + **Adapter** `adapters/snapshot/filesystem.py` — `~/.claude-prophet/snapshots/` |
| **CostCalculator** | **Domain Service** (`domain/services/cost.py`) — 순수 계산, 요율표는 Port로 주입 |
| **PricingProvider** | **Driven Port** `PricingProvider` + **Adapter** `adapters/pricing/bundled.py`·`adapters/pricing/tomloverride.py` |
| **OutcomeClassifier** | **Domain Service** (`domain/services/outcome.py`) + **Driven Port** `OutcomeRulesProvider` |
| **SessionClusterer** | **Domain Service** (`domain/services/cluster.py`) — 유사 세션 검색, best-config 추출 |
| **PostmortemAnalyzer** | **Domain Service** (`domain/services/postmortem.py`) — 성공 세션과 Δ 계산 |

**핵심 규칙 재강조** (LAYERING §2 LP-1~6):
- Domain / Use Cases / Ports는 `duckdb`·`fastapi`·`typer`·`rich`·`watchdog`·`mcp` SDK 등 third-party를 **import하지 않는다**.
- Repository 인터페이스는 Port(`ports/repositories.py`)에 정의, 구현은 Adapter에 위치.
- Harness(`harness/*_main.py`)는 조립만 — 비즈니스 로직 금지.

아래 §4.1~§4.6의 기술적 세부는 그대로이지만, 각 컴포넌트는 **Port에 의존하고 Adapter로 구현된다**는 전제 위에 있다.

### 4.1 Ingestor Layer

수집 컴포넌트는 세 종류의 소스에서 이벤트를 받아 표준화된 `RawEvent` 객체로 변환해 Storage에 저장한다.

#### 4.1.1 `hook_receiver.py`

Claude Code의 PostToolUse, Stop, UserPromptSubmit, SubagentStop 훅이 실행하는 엔트리포인트. `.claude/settings.json`에 등록된다.

**책임 범위**
- stdin으로 들어오는 훅 payload 파싱 (JSON)
- session_id, tool_name, timestamps 추출
- DuckDB에 append-only insert
- 50ms 이내 종료 (NFR-1)

**비책임**
- 집계·분석 (Analyzer가 담당)
- 파싱 실패 시 복구 (silent fail)

**인터페이스**
```bash
# Claude Code가 자동 호출
echo '<hook payload>' | ccprophet-hook
```

**설계 결정**
- Python 단일 파일. 의존성은 표준 라이브러리만 (`json`, `sqlite3` 또는 `duckdb`). cold start 비용을 최소화하기 위해 `rich`, `typer` 같은 무거운 라이브러리를 import하지 않는다.
- Buffered write는 하지 않는다. 훅은 휘발성이므로 즉시 커밋.
- Connection pooling 없음. 각 훅 호출이 독립 연결. DuckDB의 WAL이 동시성을 처리.

#### 4.1.2 `jsonl_tailer.py`

백그라운드 프로세스 또는 주기 실행 모드. `~/.claude/projects/**/*.jsonl`을 watchdog로 감시하며 새 이벤트를 DuckDB로 ingest한다.

**책임 범위**
- 신규 세션 파일 감지 (onCreate)
- append 이벤트 감지 (onModify)
- JSONL 라인 파싱 → `RawEvent` 변환
- 이미 ingest된 라인 스킵 (checkpoint 관리)

**체크포인트 메커니즘**
`~/.claude-prophet/checkpoint.json`에 `{file_path: last_byte_offset}`을 저장. 중복 insert 방지를 위해 이벤트 ID 기반 UPSERT 쿼리 사용.

**실행 모드**
- `ccprophet tail` — foreground watchdog 모드
- `ccprophet ingest --once` — 한 번만 훑고 종료 (cron 또는 `launchd` 연동)

#### 4.1.3 `otlp_bridge.py` (opt-in)

Claude Code의 `CLAUDE_CODE_ENABLE_TELEMETRY=1` + OTLP exporter가 이미 설정된 환경에서, ccprophet이 OTLP collector 역할을 해서 중복 ingest 없이 이벤트 수신.

**기본값 OFF.** `ccprophet install --otlp`로 활성화.

### 4.2 Storage Layer

단일 DuckDB 파일 `~/.claude-prophet/events.duckdb`. 모든 읽기·쓰기의 중심 허브.

**설계 결정**

*왜 DuckDB인가 (SQLite 대신)*
- 컬럼 스토어: "최근 30일 세션 중 autocompact 도달한 것" 같은 분석 쿼리에서 100~1000배 빠름
- 내장 Parquet I/O: `COPY TO 'archive.parquet'` 한 줄로 장기 아카이브
- 윈도우 함수·HyperLogLog·regex 네이티브: Analyzer 쿼리가 간결해짐
- Python/Node 바인딩 성숙, 서버 프로세스 불필요 (SQLite와 동일)

*왜 단일 파일인가*
- `scp` 가능, 백업 간단 (AP-4)
- 멀티 프로세스 읽기 지원 (DuckDB는 1.x부터 read-only concurrent connections 안정)
- 쓰기는 Ingestor만 (단일 writer) — write contention 없음

*동시성 모델*
- Writer: Ingestor 레이어 (hook_receiver 여러 인스턴스가 동시 호출 가능하지만, DuckDB가 write lock 직렬화)
- Reader: Analyzer, Viewer, MCP 모두 read-only connection
- 백업: Analyzer가 `EXPORT DATABASE` 명령으로 일별 Parquet snapshot

상세한 스키마·인덱스·파티셔닝은 `DATAMODELING.md` 참조.

### 4.3 Analyzer CLI

사용자 접점 중 가장 빈번한 경로. 모든 명령은 `ccprophet <subcommand>` 형식.

**기술 스택**
- `typer` — CLI 프레임워크. `argparse`보다 가독성·자동완성 우수.
- `rich` — 터미널 렌더링. 테이블·스파크라인·진행바·색상.
- `pyduckdb` — DuckDB Python 바인딩.

**명령 분류**

| 분류 | 명령 | 특성 |
|---|---|---|
| 라이브 뷰 | `live`, `statusline` | 단기 refresh loop, 1Hz 업데이트 |
| 분석 리포트 | `bloat`, `phase`, `diff` | 단발성 쿼리 → 렌더 |
| 예측 | `forecast` | Forecaster kernel 호출 |
| 저수준 | `query`, `export` | 고급 사용자 접근 |
| 운영 | `install`, `doctor`, `tail` | 설치·진단·백그라운드 실행 |
| 서비스 모드 | `serve`, `mcp` | 장기 실행 프로세스 |

**공통 플래그**
- `--json`: 모든 출력 JSON (머신 파싱)
- `--since`, `--until`: 시간 범위 필터
- `--session SID`: 특정 세션 지정
- `--locale`: ko / en

**Cold start 최적화**
- Python lazy import — `live` 명령이 실행될 때만 `rich` import
- DuckDB 초기화 지연 — 스키마 검증은 첫 쿼리 직전에만

### 4.4 Web Viewer

`ccprophet serve`로 localhost:8765에 HTTP 서버 실행. Work DAG 시각화가 핵심.

**아키텍처**
```
ccprophet serve
    │
    ├─ FastAPI server (localhost only, CORS disabled)
    │   ├─ GET  /api/sessions
    │   ├─ GET  /api/sessions/{sid}/dag
    │   ├─ GET  /api/sessions/{sid}/bloat
    │   └─ WS   /ws → 실시간 이벤트 push (Ingestor가 publish)
    │
    └─ Static assets (단일 index.html + bundled JS)
        ├─ D3.js v7 (force-directed)
        ├─ Cytoscape.js (대안 렌더러, 대용량 그래프용)
        └─ vanilla JS (빌드 스텝 없음)
```

**설계 결정**

*왜 React/Vue가 아닌 vanilla JS인가*
- 빌드 파이프라인 제거 → `git clone && python serve.py`만으로 돌아가야 함
- 단일 HTML 파일 배포 → CDN 의존 없음 (AP-1 Local-First)

*왜 Cytoscape.js를 Fallback으로 두는가*
- D3 force-directed는 ~500 노드에서 프레임 드랍
- 대형 엔터프라이즈 코드베이스의 하루치 세션은 2000+ 노드 가능
- 노드 수 임계치 기반 자동 전환

*실시간 업데이트 경로*
- Ingestor가 훅 insert 후 Unix domain socket으로 "changed" 시그널 발송
- Viewer의 WebSocket handler가 이를 구독
- 전체 그래프 refetch 대신 incremental patch (added/removed/updated node ID 리스트만 전송)

### 4.5 MCP Server

Claude Code가 ccprophet을 MCP 서버로 등록해 자기 자신을 분석할 수 있게 한다. AP-6의 구현체.

**프로토콜**
- stdio transport (MCP 표준)
- `ccprophet mcp` 단일 명령으로 실행

**노출 tools**

```
get_current_bloat()           → BloatReport
get_phase_breakdown(sid?)     → PhaseBreakdown
forecast_compact()            → ForecastResult
diff_sessions(sid_a, sid_b)   → SessionDiff
recommend_action()            → list[Action]
query_session_history(filter) → list[SessionSummary]
```

**제약**
- Tool 정의 총합 < 1500 tokens (스스로가 bloat가 되지 않도록)
- 모든 tool 응답 < 500ms p95
- 민감 정보 redact — 파일 경로·shell 명령은 기본적으로 hash로만 응답

### 4.6 Forecaster + Recommender (Shared Kernel)

Analyzer CLI, Web Viewer, MCP Server가 모두 공유하는 내부 모듈. 독립 실행 불가 (엔트리포인트 없음).

**Phase 1 구현 (선형)**
- 최근 5분 input token burn rate 계산 → 선형 외삽
- autocompact 임계치 (컨텍스트 80%) 도달 예상 시각 반환

**Phase 3 구현 (ARIMA)**
- `statsmodels.tsa.arima.ARIMA(1,1,1)` 기본값
- 세션별 모델을 online으로 fit (최근 N=50 관측점 rolling window)
- 훈련 비용이 무시 가능한 수준 (수십 ms)

**Recommender 로직**
단순 rule-based. 각 rule은 condition → action → confidence·근거 매핑. **반환값은 `list[Recommendation]`** (§4.7 참조).

```python
rules = [
    Rule(
        kind="prune_mcp",
        when=lambda s: s.bloat_tokens > 15_000 and s.recent_use_pct == 0,
        action=lambda s: DisableMcp(mcp=s.mcp_name, est_savings_tokens=s.bloat_tokens),
        rationale_template="최근 {days}일 호출 0회, 제거 시 {tokens:,} 토큰 절감",
    ),
    Rule(
        kind="run_clear",
        when=lambda s: s.predicted_compact_in < 300 and s.task_incomplete,
        action=lambda s: RunClear(reason="imminent autocompact"),
        rationale_template="{seconds}초 내 autocompact 도달 예상",
    ),
    # ...
]
```

모든 추천은 `Recommendation(kind, target, est_savings_tokens, est_savings_usd, confidence, rationale)` 공통 형태로 저장된다 (DATAMODELING `recommendations` 테이블). Phase 4에서 ML 기반 personalized ranker로 교체 고려.

### 4.7 Auto-Fix Kernel — SettingsPatcher + SnapshotStore

**역할**: Recommender가 생성한 `Recommendation`을 실제 파일 변경(`.claude/settings.json`, `.mcp.json`, subset profile)으로 집행. AP-7을 강제하는 유일한 쓰기 경로.

**데이터 플로우 (apply)**
```
[1] user → ccprophet prune --apply
[2] RecommendActionUseCase → list[Recommendation] (kind=prune_mcp ...)
[3] ApplyPruningUseCase:
        ├─ SnapshotStore.save(paths=[settings.json, .mcp.json], reason="prune-2026-04-17T09")
        │       → ~/.claude-prophet/snapshots/<id>/{settings.json,.mcp.json,meta.json}
        ├─ SettingsStore.read(path)
        ├─ SettingsPatcher.apply(current, recommendations) → new_content
        ├─ SettingsStore.write_atomic(path, new_content)   # tmp + rename
        └─ RecommendationRepository.mark_applied(rec_id, snapshot_id)
[4] CostCalculator.realized_savings(before=prev_session, after=null_placeholder)
[5] 사용자가 다음 세션 실행 후, next `ccprophet cost`가 realized 집계
```

**설계 결정**
- `SettingsStore.write_atomic`은 `tmp + os.replace(tmp, target)` (POSIX 원자성). Windows도 `os.replace` 원자적.
- 동시 편집 감지: `read` 시 파일 hash(SHA256) 저장, `write_atomic` 직전 재계산해 다르면 abort + 사용자에게 재시도 요구 (§11 참조).
- 스냅샷은 tarball 또는 개별 파일? → **개별 파일 디렉토리**. 파일 수 적고 replay diff가 용이.
- 스냅샷 보관: 50MB 한도, 오래된 것부터 rotation (NFR-6).
- `snapshot restore` 는 역방향 atomic write 수행.

**MCP 경로 제외**: MCP 서버는 이 컴포넌트를 절대 호출하지 않는다. CLI에서만 접근 가능 (AP-7 + FR-6.4).

### 4.8 Cost Kernel — PricingProvider + CostCalculator

**역할**: 토큰 집계를 USD(또는 사용자 통화)로 환산. 모든 명령의 `--cost` 플래그와 `ccprophet cost` 전용 명령을 지원.

**요율표 구조**
```toml
# ~/.claude-prophet/pricing.toml (사용자 override 가능)
[claude-opus-4-6]
input_per_mtok = 15.0    # USD per 1M input tokens
output_per_mtok = 75.0
cache_write_per_mtok = 18.75
cache_read_per_mtok = 1.50

[claude-sonnet-4-6]
input_per_mtok = 3.0
output_per_mtok = 15.0
```

**계산**
- `session_cost = input_tokens * rate_in + output_tokens * rate_out + cache_costs` (USD).
- `realized_savings = cost(session_pre_prune_avg) - cost(session_post_prune)` (실측).
- `estimated_savings = sum(rec.est_savings_usd) for rec in unapplied` (예측).
- 결과는 `pricing_rates` 테이블에 사용 요율을 함께 stamp해 추후 감사 가능.

**설계 결정**
- 기본 요율표는 PyPI 패키지에 번들 (`ccprophet/data/pricing.toml`). 업데이트는 **패키지 릴리즈로만** 반영 (네트워크 차단).
- 모델 미매칭 시 `UnknownPricingError` → CLI가 `-`로 표시, JSON은 `null`.
- 통화 변환: 고정 환율 테이블, 사용자 `pricing.toml`에서 override. 기본은 USD 고정.

### 4.9 Outcome Engine — Clusterer + Classifier + Postmortem

**역할**: "결과가 더 잘 나오는 방식"을 학습·재현. Session Optimizer 제품(Phase 1 MVP 제품 B)의 핵심 커널.

**구성**
- **OutcomeClassifier**: 세션의 outcome label을 결정. 입력 = 사용자 수동 라벨 + 규칙 엔진. 규칙 예: autocompact 도달 = 부분실패, 같은 파일 5회+ re-read = 실패 힌트.
- **SessionClusterer**: `(task_type, project_slug, model)` 튜플 기준으로 세션 클러스터링. 성공 라벨이 n≥3 이상인 클러스터만 "best config" 추출 대상.
- **BestConfigExtractor**: 클러스터 내 공통 MCP subset, phase 분포 중위값, `/clear` 타이밍을 `BestConfig` 엔티티로 집약.
- **PostmortemAnalyzer**: 실패 세션 하나와 유사 성공 세션 집합의 Δ를 계산해 `PostmortemReport` (structured) 반환.

**데이터 플로우 (reproduce)**
```
[1] user → ccprophet reproduce refactor-auth --apply
[2] ReproduceSessionUseCase:
        ├─ SessionClusterer.find_cluster(task_type="refactor-auth")  → list[Session]
        ├─ BestConfigExtractor.extract(cluster)                      → BestConfig
        ├─ (if --apply) Auto-Fix Kernel을 통해 settings.json patch
        └─ Recommendation 테이블에 provenance 기록 (reason="reproduce:refactor-auth")
```

**설계 결정**
- 클러스터링은 SQL로 충분 (GROUP BY + 조건). ML 라이브러리 불필요.
- outcome 규칙 엔진은 `~/.claude-prophet/outcome_rules.toml`로 사용자 커스터마이즈.
- Phase 3에서 prompt 기반 자동 태깅 실험 (F8/F11 공통).

## 5. 데이터 플로우 (Data Flow)

**이벤트 하나의 수명주기**

```
[1] Claude Code tool_use 실행
        │
        ▼
[2] PostToolUse hook 발화
        │
        ▼
[3] hook_receiver.py (stdin에서 JSON 수신)
        │   └─ session_id, tool_name, input_hash, latency 추출
        ▼
[4] DuckDB INSERT INTO events + tool_calls
        │
        ▼
[5] Unix socket으로 "event_added" 시그널
        │
        ├────────────────────┬──────────────────┐
        ▼                    ▼                  ▼
[6a] Viewer WebSocket    [6b] MCP 서버가    [6c] 다음 CLI 호출이
     구독자에게 push          캐시 무효화         새 데이터 조회
        │
        ▼
[7] 브라우저 DAG 렌더 업데이트
```

**Backfill 플로우 (historical)**

```
[1] ccprophet ingest --once 실행
        │
        ▼
[2] jsonl_tailer가 ~/.claude/projects/ 스캔
        │
        ▼
[3] checkpoint.json 조회로 이미 ingest된 부분 스킵
        │
        ▼
[4] 각 JSONL 라인 → RawEvent 변환
        │
        ▼
[5] 배치 INSERT (1000 rows at a time)
        │
        ▼
[6] checkpoint.json 업데이트
```

**Auto-Fix 플로우 (prune --apply)**

```
[1] ccprophet prune --apply
        │
        ▼
[2] RecommendActionUseCase — rule 엔진으로 후보 생성
        │    (각 Recommendation에 confidence·rationale·est_savings_usd)
        ▼
[3] 사용자 확인 프롬프트 (--yes 없으면 interactive)
        │
        ▼
[4] ApplyPruningUseCase
        ├─ SnapshotStore.save(files=[settings.json, .mcp.json], reason=...)
        │       ~/.claude-prophet/snapshots/<uuid>/ 에 파일 복사
        ├─ SettingsStore.read+hash → hash_before
        ├─ SettingsPatcher.apply(current, recs) → new_content
        ├─ re-read+hash → 변경 감지 시 ABORT (concurrent edit)
        ├─ SettingsStore.write_atomic(tmp + os.replace)
        └─ RecommendationRepository.mark_applied(ids, snapshot_id)
        │
        ▼
[5] 사용자에게 요약: applied N건, snapshot=<id>, `snapshot restore <id>` 안내
```

**Cost 플로우 (ccprophet cost --month)**

```
[1] ccprophet cost --month 2026-03
        │
        ▼
[2] ComputeCostUseCase
        ├─ SessionRepository.list_in_range(2026-03-01, 2026-04-01)
        ├─ PricingProvider.load(model) for each session.model
        ├─ CostCalculator.session_cost(session, rates)
        └─ 집계: total_cost, realized_savings (prune 전후), estimated_savings
        │
        ▼
[3] rich table + `(saving: $XX)` 라벨 렌더
```

**Outcome 재현 플로우 (reproduce --apply)**

```
[1] ccprophet reproduce refactor-auth --apply
        │
        ▼
[2] ReproduceSessionUseCase
        ├─ OutcomeRepository.success_sessions(task_type="refactor-auth")
        ├─ (n < 3) → insufficient data 종료
        ├─ SessionClusterer.cluster(...)
        ├─ BestConfigExtractor.extract(cluster) → BestConfig
        ├─ Recommendation으로 변환 → Auto-Fix Kernel로 위임 (AP-7)
        └─ Postmortem 없음 (postmortem은 별도 명령)
```

## 6. 기술 스택 선택 근거 (Tech Stack Rationale)

| 계층 | 선택 | 대안 | 선택 근거 |
|---|---|---|---|
| 언어 | Python 3.10+ | Go, Rust, TypeScript | ccusage 생태계 호환성, 데이터 분석 라이브러리 풍부, 훅 스크립트 공통 관례 |
| DB | DuckDB | SQLite, Postgres | 분석 쿼리 성능, 단일 파일, Parquet 네이티브, 서버 불필요 |
| CLI 프레임워크 | typer | argparse, click | 타입 힌트 기반, 자동완성, 가독성 |
| 터미널 렌더링 | rich | textual, blessed | 간결, 표·차트·색상 내장 |
| 파일 감시 | watchdog | pyinotify, polling | 크로스 플랫폼, 검증된 라이브러리 |
| 웹 프레임워크 | FastAPI | Flask, aiohttp | 타입 힌트, WebSocket 내장, async |
| 프론트엔드 | vanilla JS + D3 + Cytoscape | React, Vue | 빌드 스텝 제거, 단일 HTML 배포 |
| MCP SDK | Anthropic MCP Python SDK | 자체 구현 | 공식 SDK, 프로토콜 변경 추적 용이 |
| 예측 모델 | statsmodels ARIMA | Prophet, LSTM | 경량, 훈련 빠름, 해석 가능 |

## 7. 통합 지점 (Integration Points)

### 7.1 Claude Code Hooks

`.claude/settings.json`에 등록되는 훅. `ccprophet install`이 자동 등록한다.

```json
{
  "hooks": {
    "PostToolUse": [
      {"type": "command", "command": "ccprophet-hook --event PostToolUse", "timeout": 10}
    ],
    "Stop": [
      {"type": "command", "command": "ccprophet-hook --event Stop", "timeout": 10}
    ],
    "UserPromptSubmit": [
      {"type": "command", "command": "ccprophet-hook --event UserPromptSubmit", "timeout": 5}
    ],
    "SubagentStop": [
      {"type": "command", "command": "ccprophet-hook --event SubagentStop", "timeout": 10}
    ]
  }
}
```

### 7.2 Claude Code JSONL

`~/.claude/projects/<project-slug>/<session-uuid>.jsonl` 파일. 각 라인이 하나의 event.

Ingestor는 이 파일 포맷을 **읽기 전용으로만** 다룬다. 수정·삭제하지 않는다.

### 7.2.1 `.claude/settings.json` — 자동 패치 대상

Auto-Fix Kernel만이 쓰기를 수행한다. 규칙:

- **원자성**: `write_atomic` = 같은 디렉토리에 `.settings.json.<uuid>.tmp` 생성 후 `os.replace` (POSIX·Windows 모두 원자적).
- **hash guard**: read 시 SHA256 기록, write 직전 재비교 → 다르면 abort.
- **스냅샷 선행 필수**: snapshot_id 없이 write 호출 시 assertion 실패.
- **백업 보관**: 각 apply마다 `~/.claude-prophet/snapshots/<id>/settings.json` 저장. rotation은 50MB 초과 시 오래된 snapshot 디렉토리 삭제.
- **포맷 보존**: 사용자 들여쓰기·주석(JSON5 아님, 표준 JSON) 유지. `json.dump(indent=2, sort_keys=False)`로 write.

### 7.2.2 `.mcp.json` — 동일 정책

`.mcp.json`은 `.claude/settings.json`과 동일한 패치·스냅샷 규칙을 따른다. MCP 서버 비활성화는 두 파일 중 하나에만 적용 가능한 경우가 있어 `SettingsStore` 구현이 경로별 schema를 분기 처리한다.

### 7.3 OpenTelemetry (opt-in)

Claude Code가 OTLP로 emit하는 이벤트를 받는 경로. `ccprophet install --otlp`로 활성화 시:
- 로컬 OTLP collector (gRPC :4317)를 ccprophet이 띄운다
- Claude Code 설정에 `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` 자동 추가
- 훅 경로와 중복이면 OTLP 경로 우선 (더 풍부한 메타데이터)

### 7.4 MCP 등록

사용자가 `.claude/mcp_servers.json`에 ccprophet을 MCP 서버로 등록:

```json
{
  "mcpServers": {
    "ccprophet": {
      "command": "ccprophet",
      "args": ["mcp"],
      "env": {}
    }
  }
}
```

`ccprophet install --mcp`가 자동 등록.

## 8. 배포 및 운영 (Deployment & Operations)

### 8.1 설치 경로

```bash
# 권장 — 격리된 환경
pipx install ccprophet

# 또는 uv
uv tool install ccprophet

# 일회성 실행
uvx ccprophet bloat

# 설치 후 한 번 실행
ccprophet install
# └─ 훅 등록, MCP 등록, DuckDB 초기화, 체크포인트 생성
```

### 8.2 디렉토리 레이아웃

```
~/.claude-prophet/
├── events.duckdb              # 주 저장소
├── events.duckdb.wal          # DuckDB WAL
├── checkpoint.json            # jsonl_tailer 진행 상태
├── config.toml                # 사용자 설정
├── pricing.toml               # Cost Kernel override (없으면 번들 기본값)
├── outcome_rules.toml         # Outcome Classifier 규칙 override
├── snapshots/
│   ├── 2026-04-17T09-12-33-abc123/
│   │   ├── meta.json          # reason, applied_recs, target_paths
│   │   ├── settings.json      # 적용 직전 원본
│   │   └── .mcp.json          # (있었다면)
│   └── ...                    # 50MB rotation
├── profiles/
│   ├── refactor.json          # subset profile (F7/F11 산출)
│   └── review.json
├── archive/
│   ├── 2026-04-15.parquet     # 일별 DuckDB 스냅샷
│   └── ...
└── logs/
    └── ccprophet.log          # 운영 로그 (rotate)
```

### 8.3 업그레이드 정책

- SemVer 준수
- 스키마 변경은 minor 버전 증가 + 자동 마이그레이션 (`ALTER TABLE ...`)
- `ccprophet doctor` 명령이 버전 호환성 점검 및 복구

### 8.4 모니터링

ccprophet 자신의 운영 메트릭을 별도 테이블 `prophet_self_metrics`에 기록한다. (Dogfooding)

- 훅 실행 시간 p50/p95/p99
- DuckDB 파일 크기
- Ingestor 누락 이벤트 수
- Forecaster MAE

`ccprophet doctor`가 이 지표를 요약 출력.

## 9. 보안 및 프라이버시 (Security & Privacy)

### 9.1 위협 모델

| 위협 | 완화 |
|---|---|
| DuckDB 파일 유출 | OS 파일 권한 600 (`chmod 600`), 옵션으로 age 암호화 |
| 로컬 악성 프로세스가 읽기 | 동일 사용자 계정 내 격리는 불가능, 파일 권한으로만 방어 |
| 프롬프트·tool 출력에 PII | 기본 redact (파일 경로, 명령 인자는 SHA256 hash로 저장) |
| 웹 서버가 원격 노출 | 항상 127.0.0.1 bind, 0.0.0.0 바인드 불가 |
| MCP 서버가 쓰기 작업 수행 | 모든 MCP tool은 read-only, 쓰기 tool 존재하지 않음 |

### 9.2 Redaction 정책

**기본 redact 대상**
- `tool_input.file_path` → `<hash:abc123>`
- `tool_input.command` (Bash) → 명령어 첫 단어만 유지
- `user_prompt.content` → 길이만 저장, 본문 저장 안 함

**Opt-in으로만 저장**
```toml
# ~/.claude-prophet/config.toml
[redaction]
store_file_paths = false  # true로 명시해야 파일 경로 저장
store_prompt_content = false
store_command_args = false
```

### 9.3 오프라인 모드

`CCPROPHET_OFFLINE=1` 환경변수가 설정되면:
- OTLP bridge 비활성화
- 외부 이미지·폰트 로딩 차단 (Web Viewer)
- 패키지 업데이트 체크 없음

## 10. 확장성 (Extensibility)

### 10.1 Plugin Hook Points

```python
# ~/.claude-prophet/plugins/my_plugin.py
from ccprophet.plugin import plugin

@plugin.on_event("PostToolUse")
def enrich_tool_call(event: RawEvent) -> RawEvent:
    # 사용자 정의 enrichment
    return event

@plugin.analyzer("custom_bloat")
def custom_bloat_rule(session) -> BloatReport:
    # 조직별 bloat 기준 추가
    pass
```

### 10.2 Adapter Pattern for Future Agents

v1은 Claude Code 전용. Phase 4에서 다른 agent 지원.

```
ccprophet/
├── adapters/
│   ├── claude_code.py    # v1
│   ├── codex.py          # v2
│   ├── opencode.py       # v2
│   └── base.py           # 인터페이스 정의
```

각 adapter는 agent-specific JSONL/hook 포맷을 공통 `RawEvent`로 변환.

## 11. 장애 모드 (Failure Modes)

| 장애 | 감지 | 복구 |
|---|---|---|
| DuckDB 파일 손상 | 연결 시 예외 | `ccprophet doctor --repair`가 최신 Parquet 스냅샷에서 복구 |
| 훅 스크립트 timeout | Claude Code가 10초 후 kill | silent fail, 다음 이벤트는 정상 처리 |
| jsonl_tailer가 파일 누락 | checkpoint와 ls 비교 | 수동 `ccprophet ingest --force` |
| Web Viewer 크래시 | 프로세스 exit | 사용자가 재실행 (자동 재시작 없음) |
| MCP 서버 행 | Claude Code가 timeout 후 연결 끊음 | ccprophet MCP 프로세스 재기동 |
| JSONL 스키마 변경 | 파싱 실패 로그 | adapter 업그레이드 배포, 실패 이벤트는 `raw_fallback` 테이블에 보존 |
| 디스크 full | Ingestor 쓰기 실패 | 오래된 Parquet 아카이브 자동 삭제 (옵션) |
| **settings.json 동시 편집 충돌** | `write_atomic` 직전 hash 변경 | apply abort, 사용자에게 "외부에서 수정됨, 재실행하세요" 메시지 + snapshot 저장 건너뜀 |
| **스냅샷 디스크 한도 초과** | 50MB 초과 감지 | 오래된 snapshot부터 삭제, 최근 10건은 최소 보존 |
| **pricing.toml 파싱 실패** | CostKernel 초기화 예외 | 번들 기본 요율로 fallback + 경고 로그 |
| **Outcome 샘플 n<3** | ReproduceUseCase에서 체크 | `insufficient data, try n>=3` 메시지 반환 (무한추정 방지) |
| **Recommendation apply 후 rollback 필요** | 사용자가 `snapshot restore` 호출 | snapshot 디렉토리에서 파일 역복원, atomic write |

## 12. 성능 목표와 병목 분석

### 12.1 목표 수치 (NFR 재확인)

| 메트릭 | 목표 | 측정 방법 |
|---|---|---|
| 훅 실행 시간 p99 | < 50ms | `prophet_self_metrics` 테이블 |
| CLI cold start | < 500ms | `time ccprophet bloat` |
| DAG render (500 노드) | < 1s | 브라우저 performance API |
| DAG render (2000 노드) | < 3s | 동일 |
| 30일 세션 bloat 쿼리 | < 2s | DuckDB EXPLAIN ANALYZE |
| MCP tool 응답 p95 | < 500ms | MCP 서버 내부 타이머 |

### 12.2 예상 병목과 대응

**병목 1: 훅 실행 시간**
원인: Python cold start, DuckDB 연결 오픈
대응:
- Python 최소 import (stdlib만)
- DuckDB pragma `memory_limit='256MB'`로 메모리 튜닝
- 장기적: Rust로 hook_receiver 재작성 검토

**병목 2: 대형 세션 DAG 렌더링**
원인: D3 force simulation이 O(n²)
대응:
- 노드 수 임계치 (500) 초과 시 Cytoscape.js로 자동 전환
- 커뮤니티 집계 (community detection)로 논리 그룹핑
- Virtual scrolling

**병목 3: DuckDB 파일 비대화**
원인: 90일 이상 축적 시 수 GB
대응:
- 90일 넘으면 `tool_calls`, `events`의 상세 payload를 aggregate 테이블로 roll-up
- 원본은 Parquet으로 오프로드
- 상세는 `DATAMODELING.md` 참조

## 13. 오픈 아키텍처 결정 사항 (Open ADRs)

향후 별도 ADR 문서로 기록할 항목:

- **ADR-001**: DuckDB vs SQLite — 분석 워크로드 최적화로 DuckDB 선택, 단 단일 writer 가정 필요.
- **ADR-002**: vanilla JS vs React — 빌드 스텝 제거로 vanilla 선택, 컴포넌트 재사용성은 포기.
- **ADR-003**: Python vs Rust for hooks — Python으로 시작, 50ms 목표 미달 시 Rust 재작성.
- **ADR-004**: Local-only 원칙의 한계 — 팀 단위 집계 요구 발생 시, 별도 repo `ccprophet-team`으로 분리할지 이 repo에 flag로 넣을지.
- **ADR-005**: Schema evolution — breaking change 시 migration 자동화 vs 수동 `doctor` 명령.
- **ADR-006**: Clean Architecture + Hexagonal 결합 — 계층 규칙·의존성 방향·테스트 전략은 `LAYERING.md`로 분리 관리. `import-linter`로 CI 강제.
- **ADR-007**: settings.json 패치는 포맷-보존(JSON 표준 `indent=2`) vs 주석 보존(json5/jsonc). 결정: 표준 JSON만 지원. 주석이 있으면 apply abort + 사용자에게 안내.
- **ADR-008**: Pricing 요율 source — 네트워크 fetch 금지. 패키지 번들 + 사용자 toml override만.
- **ADR-009**: Outcome 라벨 자동 규칙의 기본 set — 최소주의. autocompact 도달 = partial, 사용자 수동만 success/fail. 확장은 사용자가 `outcome_rules.toml`로.
- **ADR-010**: Auto-Fix의 적용 권한 — MCP 경로는 영구히 read-only. CLI만 apply 가능 (NFR-9, FR-6.4).
- **ADR-011**: Snapshot 보관 포맷 — tar.gz vs 디렉토리. 결정: 디렉토리 (diff 용이, 개별 파일 restore 가능).

---

**문서 종료**
