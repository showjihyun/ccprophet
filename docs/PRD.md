# ccprophet — Context Efficiency **Advisor** for Claude Code

**요구사항 및 기능 정의서 (PRD)**

| 항목 | 내용 |
|---|---|
| 문서 버전 | 0.5 (Quality Watch) |
| 작성일 | 2026-04-17 |
| 프로덕트 이름 | `ccprophet` |
| 대상 플랫폼 | Claude Code (macOS / Linux / Windows WSL), 로컬 PC 전용 |
| 라이선스 방향 | MIT (오픈소스) |

**Naming**: `cc` (Claude Code 관례 — ccusage, ccmonitor) + `prophet` (예측·예언, 자동 추천) + `profit`·`profile`의 음운적 연상. **측정 → 예측 → 추천 → 액션**이라는 4단 파이프라인을 한 단어에 담았다.

**한 줄 정의**: *ccprophet은 Claude Code 세션의 낭비(bloat)를 자동으로 없애고, 더 좋은 결과가 나오는 방식을 학습시켜주며, 절약된 토큰을 **달러**로 환산해 보여주는 로컬 옵티마이저다.*

**네 문장 약속**
1. **"알려주는 것"이 아니라 "자동으로 고친다"** — MCP 비활성화, subset config, `/clear` 추천까지 한 번에 apply 가능.
2. **"얼마나 썼나"가 아니라 "결과가 더 잘 나왔나"** — 성공한 세션의 config와 phase 패턴을 학습해 best config를 재현한다.
3. **"토큰 수"가 아니라 "달러"** — 절약 효과를 월 단위 $로 환산해 의사결정을 쉽게 만든다.
4. **"Anthropic이 구라 못 치게"** — 동일 모델·동일 옵션에서 주간/월간 품질 지표가 유의미하게 떨어지면 **자동으로 플래그를 띄운다**. 다운그레이드 가설을 데이터로 검증한다.

---

## 1. 배경 (Background)

Claude Code는 200k~1M 토큰 컨텍스트 윈도우를 소비하는 방식으로 동작하며, 사용자는 `/context`, `/usage`, `/stats` 같은 빌트인 명령과 `ccusage`, `Claude-Code-Usage-Monitor`, `claude-context-monitor` 같은 서드파티 도구를 통해 사용량을 모니터링한다. 멀티 에이전트 관측성 측면에서도 `disler/claude-code-hooks-multi-agent-observability`, `simple10/agents-observe`, `patoles/agent-flow` 등이 이미 시장에 자리잡았다.

그러나 이 도구들은 공통적으로 **"얼마나 썼나"**만 측정하고, **"얼마나 잘 썼나"**는 답하지 못한다. 로딩된 MCP tool 중 실제로 호출된 비율, 읽었지만 응답에 반영되지 않은 파일, 페이즈별 토큰 분포, autocompact 이벤트 예측 같은 **효율 관점의 분석**이 비어 있다. Anthropic이 `/context`와 activity dashboard를 네이티브로 흡수하는 추세 속에서 살아남으려면 단순 카운터가 아니라 **액션 제안까지 하는 옵티마이저**로 포지셔닝해야 한다.

그리고 더 중요한 사실: **측정만으로는 유틸리티가 되지 않는다.** bloat 37%라는 숫자를 보여줘도, 어떤 MCP를 끄고 어떤 tool subset을 쓸지 결정하는 노동은 여전히 사용자 몫이다. v0.2 PRD는 이 간극을 놓쳤다. v0.3은 그 간극을 제 1 요구사항으로 승격시킨다 — **측정 → 예측 → 추천 → (옵션) 자동 적용**.

## 2. 문제 정의 (Problem Statement)

Claude Code 파워 유저는 다음 **다섯 가지** 고통을 반복적으로 겪는다.

1. **보이지 않는 Bloat** — `/context`가 MCP tools 26k 토큰을 소비한다고 알려줘도, 그중 실제로 호출된 tool이 몇 개인지는 알 수 없다. 세션 내내 한 번도 쓰지 않은 tool 정의가 컨텍스트를 갉아먹는다.
2. **구조 불투명성** — 현재 세션에서 Subagent가 몇 개 떠 있고, 각각 어떤 파일과 MCP 서버에 의존하는지 그래프로 볼 수단이 없다. 기존 도구들은 타임라인 위주라 의존 구조를 보여주지 못한다.
3. **페이즈 단위 측정 부재** — 개발자는 "이 리팩토링 작업이 45k 소비, 그중 플래닝 12k / 구현 27k / 리뷰 6k"처럼 작업 단위로 보고 싶지만, 모든 도구가 세션 혹은 일 단위로만 집계한다.
4. **사후 분석 불가** — `~/.claude/projects/**/*.jsonl`에 모든 세션이 쌓여 있지만, "최근 30일 세션 중 autocompact 도달한 것들의 공통 패턴"을 쿼리할 수 있는 도구가 없다.
5. **측정이 행동으로 이어지지 않음** — bloat 리포트를 받아도 어떤 MCP를 비활성화할지, 어느 phase에서 `/clear`할지, 이 작업에 어떤 tool subset이 필요할지는 여전히 수동 판단이다. 관측과 행동 사이의 간극이 도구를 일회성으로 만든다.
6. **결과 품질이 블랙박스** — 사용자가 실제로 알고 싶은 건 "이 세팅으로 하면 결과가 더 잘 나오느냐"다. 그러나 어떤 config가 성공 세션을 만들었고 어떤 패턴이 실패로 이어졌는지 추적·재현할 수단이 없다.
7. **비용 감각 부재** — 토큰 숫자는 피부에 안 와닿는다. "지난달 $180 썼고 이 중 $52는 사용되지 않은 MCP에 지출됐다"처럼 **달러**로 보여줘야 행동을 유발한다. 현재 모든 도구가 토큰 단위에만 머문다.

## 3. 목표 및 비목표 (Goals / Non-Goals)

### 3.1 Goals

- Claude Code 세션의 **컨텍스트 효율성**을 실시간과 사후 양쪽에서 측정 가능하게 한다.
- **"알려주기"에서 "자동으로 고치기"로 이동한다** — bloat를 탐지하면 settings.json/.mcp.json 패치까지 자동 생성·적용.
- **결과 품질 개선을 1급 목표로 한다** — 성공한 세션의 config·phase 패턴을 학습해 다음 세션에 재현시키는 outcome engine 내장.
- **모든 효용을 달러($)로 정량화한다** — 토큰 절감 = 월 예상 절약액으로 변환해 노출.
- 완전 로컬 동작 (서버/클라우드 불필요)을 기본 원칙으로 한다.
- CLI·상태바·그래프 웹뷰·MCP 서버 네 가지 접점을 모두 제공한다.
- 기존 `ccusage` 수준의 "설치 없이 npx/uvx로 즉시 실행" 사용성을 유지한다.
- Claude Code가 ccprophet를 MCP로 호출해 스스로 자기 세션을 분석·추천할 수 있게 한다 (self-introspection loop).
- **모든 자동 변경은 원복 가능해야 한다** — settings.json 패치, subset 프로필 적용 등은 스냅샷 기반 rollback 지원 필수.

### 3.2 Non-Goals

- Anthropic API 비용 청구/정산 대체 (이미 Console이 담당).
- 팀 단위 대시보드·SaaS·원격 동기화 (의도적으로 로컬 전용).
- Claude Code 외 다른 에이전트 (Codex, OpenCode 등) 1차 지원 (v2 고려).
- Graphify/axon 같은 코드베이스 Knowledge Graph 생성 (별개 도구).
- **사용자 동의 없는 자동 변경 금지** — `--apply` 플래그가 명시된 경우에만 settings.json 수정. MCP 서버 모드는 read-only 유지.

## 4. 사용자 정의 (Target Users)

| 페르소나 | 상황 | 핵심 Job-to-be-Done |
|---|---|---|
| **파워 유저 개발자** | 하루 5~10시간 Claude Code, Max 플랜, 여러 worktree | 컨텍스트 한계로 인한 병목 제거, 세션당 생산성 극대화 |
| **엔터프라이즈 도입 리드** | 온프렘 Claude Code, 팀 20~200명 | 팀 평균 토큰 낭비 지표 확보, MCP 서버 구성 최적화 판단 |
| **AI 도구 연구자** | 프롬프트 엔지니어링·컨텍스트 엔지니어링 | 자신의 작업 패턴 객관적 측정, A/B 실험 |
| **공공기관 개발자** | 망 분리, 외부 전송 금지 | 로컬 전용 원칙의 관측성 도구 |

## 5. 경쟁 지형 및 차별화

### 5.1 기존 도구 매핑

| 카테고리 | 대표 도구 | 강점 | 한계 |
|---|---|---|---|
| 빌트인 명령 | `/context`, `/stats`, `/usage` | 즉시 사용, 공식 지원 | 스냅샷, 로그 없음, 효율 분석 없음 |
| CLI 모니터 | `ccusage`, `Claude-Code-Usage-Monitor` | 경량, 리치 UI, 예측 | 토큰 카운터 중심, 효율성 ∅ |
| 컨텍스트 훅 | `MidniteJesus/claude-context-monitor` | 임계치 기반 handoff 자동화 | 단일 세션, 분석 ∅ |
| 멀티 에이전트 관측성 | `disler/...-observability`, `simple10/agents-observe` | 실시간 이벤트 스트리밍 | 서버 필요 (Bun/Docker), 타임라인 중심 |
| 그래프 시각화 | `patoles/agent-flow` | Canvas UI, JSONL replay | 시간축 중심, 구조축 ∅, 효율 분석 ∅ |
| OpenTelemetry | Anthropic 공식 OTLP export | 표준, Datadog/Honeycomb 연동 | 백엔드 필요, 로컬 분석에 과한 세팅 |

### 5.2 ccprophet의 차별화 7축

1. **Loaded vs Referenced 분석** — 로딩된 tool/파일/MCP 중 실제 호출·참조된 비율을 세션 단위로 측정한다. Bloat 자동 식별.
2. **Work DAG 시각화** — 시간축이 아닌 **구조축**. Session → Subagent → Tool → File/MCP의 의존 그래프. 노드 크기 = 토큰 기여도.
3. **완전 로컬 + DuckDB** — 서버 프로세스 없음. `~/.claude-profiler/events.duckdb` 단일 파일. 컬럼 스토어로 30일 세션 분석 쿼리도 수백 ms.
4. **Phase-aware Profiling** — Task tool 호출, 슬래시 커맨드, 사용자 prompt 경계를 phase marker로 자동 감지해 페이즈별 breakdown 제공.
5. **Forecasting + Session Replay** — autocompact까지 남은 시간 예측, 성공·실패 세션을 나란히 replay해 패턴 학습.
6. **Auto-Fix Engine** — 핵심 차별점. bloat를 *찾기만* 하는 것이 아니라 **자동으로 settings/MCP config를 수정한다**. 단순 추천이 아니라 patch → snapshot → rollback 전체 라이프사이클 제공. 과거 세션 기반으로 작업별 토큰 budget을 미리 예측하고, MCP/tool subset 프로필을 생성한다.
7. **Outcome + Cost Accountability** — "얼마나 썼나"를 넘어 **"결과가 더 잘 나왔나"와 "얼마 절약했나($)"** 두 축을 동시에 본다. 성공 세션 패턴을 재현하는 outcome engine과 토큰→달러 환산 대시보드를 결합해 "돈 냄새"를 만든다.

## 6. 기능 요구사항 (Feature Requirements)

### 6.1 F1. Ingestor — 이벤트 수집

Claude Code의 PostToolUse, Stop, UserPromptSubmit, SubagentStop 훅을 구독해 이벤트를 DuckDB에 append한다. 추가로 `~/.claude/projects/**/*.jsonl`을 주기적으로 tail해 과거 세션도 backfill한다.

**기능 요구사항**

- FR-1.1: Python 훅 스크립트 단일 파일 (50줄 이하, 의존성은 duckdb·watchdog만).
- FR-1.2: 훅 실행 시간 50ms 미만 (Claude Code 체감 지연 없음).
- FR-1.3: JSONL tailer가 파일 회전·삭제에도 견딤 (watchdog 기반).
- FR-1.4: OTLP export 설정이 이미 있으면 중복 수집 안 함 (OTLP → DuckDB 브리지 모드 옵션).
- FR-1.5: `ccprophet install`로 `.claude/settings.json`에 훅 자동 등록.

### 6.2 F2. Storage — DuckDB 스키마

단일 파일 `~/.claude-profiler/events.duckdb`. 핵심 테이블:

- `sessions` — session_id, project_slug, worktree_path, model, started_at, ended_at
- `events` — event_id, session_id, event_type, timestamp, payload_json
- `tool_calls` — tool_call_id, session_id, tool_name, input_hash, latency_ms, success
- `tool_defs_loaded` — session_id, tool_name, tokens, source (system/mcp/custom)
- `file_reads` — session_id, file_path, tokens, referenced_in_output (bool)
- `phases` — session_id, phase_id, phase_type, start_ts, end_ts, input_tokens, output_tokens
- `forecasts` — session_id, ts, predicted_compact_at, confidence

**기능 요구사항**

- FR-2.1: 스키마는 Parquet export 호환 (장기 아카이브용).
- FR-2.2: 90일 보관 후 자동 요약 테이블로 roll-up.
- FR-2.3: 세션 하나당 평균 추가 용량 < 500KB.

### 6.3 F3. Analyzer CLI

모든 분석의 1차 관문. `ccprophet` 하나의 엔트리포인트.

| 커맨드 | 기능 |
|---|---|
| `ccprophet live` | 현재 세션 실시간 토큰·bloat·예측 터미널 출력 (Rich UI) |
| `ccprophet bloat [--session SID]` | Loaded vs Referenced 리포트, 제거 후보 MCP/tool 목록 |
| `ccprophet phase [--session SID]` | 페이즈별 토큰 breakdown 테이블 |
| `ccprophet forecast` | 현재 세션 autocompact 예측, 권장 액션 |
| `ccprophet recommend [--session SID]` | **액션 우선순위 리스트** — pruning·clear·subset 등 추천 |
| `ccprophet prune [--apply] [--session SID]` | **Auto Tool Pruning** — settings.json 패치 (dry-run 기본) |
| `ccprophet budget <TASK_TYPE>` | **Context Budget Optimizer** — 과거 기반 예상 토큰·tool subset 제안 |
| `ccprophet replay SID [--compare SID_B]` | 세션 Replay. `--compare`로 **diff replay** |
| `ccprophet diff SID_A SID_B` | 두 세션 설정·효율 차이 비교 (텍스트 요약) |
| `ccprophet snapshot list\|restore ID` | 자동 변경 스냅샷 조회·원복 |
| `ccprophet quality [--window 7d --baseline 30d]` | **Quality Watch** — 모델 품질 지표 시계열 + 회귀 감지 |
| `ccprophet cost [--month YYYY-MM]` | **Cost Dashboard** — 월별 $ 사용·절약 요약 |
| `ccprophet mark SID --outcome success\|fail` | 세션 라벨링 (Outcome Engine 학습용) |
| `ccprophet reproduce TASK_TYPE [--apply]` | 성공 패턴 best config 재현 |
| `ccprophet postmortem SID` | 실패 세션 분석 — 유사 성공 세션과 비교 |
| `ccprophet query "SQL"` | DuckDB 직접 쿼리 (고급 사용자) |
| `ccprophet export --parquet PATH` | 장기 아카이브 |
| `ccprophet statusline` | 상태바 한 줄 출력 (Claude Code statusLine 통합용) |
| `ccprophet serve [--port 8765]` | 로컬 웹 DAG 뷰 + Replay UI 서빙 |
| `ccprophet mcp` | stdio MCP 서버 모드 (Claude Code가 자기 분석용으로 호출) |
| `ccprophet install` | 훅 자동 등록 |

**기능 요구사항**

- FR-3.1: 각 명령 cold-start 500ms 미만.
- FR-3.2: `--json` 플래그로 모든 출력 머신 파싱 가능.
- FR-3.3: 한국어/영어 메시지 전환 `CCPROF_LOCALE` 환경변수.

### 6.4 F4. Work DAG 웹뷰

`ccprophet serve`가 포트 8765에 로컬 웹서버를 띄운다. 인증·CORS 없음 (localhost only).

**시각화 사양**

- D3 force-directed 또는 Cytoscape.js 기반.
- 루트 노드: Session. 자식: Subagent, Phase. 리프: Tool call, File read, MCP server.
- 노드 크기 = 컨텍스트 기여 토큰 (로그 스케일).
- 엣지 두께 = 호출/참조 횟수.
- 호버 시 툴팁 — tokens loaded, tokens referenced, utilization %.
- 클릭 시 사이드 패널 — 원본 JSONL 조각, bloat 상세.
- WebSocket 구독으로 실시간 업데이트 (훅 이벤트 push).

**기능 요구사항**

- FR-4.1: 단일 HTML + vanilla JS (빌드 스텝 없음).
- FR-4.2: 동시 세션 10개까지 탭으로 구분 표시.
- FR-4.3: 스크린샷·SVG export 지원.
- FR-4.4: 외부 네트워크 호출 0회 (모든 에셋 로컬).

### 6.5 F5. Forecasting

현재 세션의 토큰 사용 곡선과 tool call rate로 autocompact 도달 시간을 예측한다.

**기능 요구사항**

- FR-5.1: Phase 1은 단순 선형 회귀 + 최근 5분 burn rate.
- FR-5.2: Phase 3에서 ARIMA 혹은 경량 신경망 모델로 업그레이드.
- FR-5.3: 예측 정확도 MAE ±3분 이내 (세션의 마지막 20%에서 측정).
- FR-5.4: 추천 액션 제공: `/clear`, `/compact focus`, MCP 서버 disable, subagent 위임.

### 6.6 F6. MCP 서버 모드

Claude Code가 `ccprophet`를 MCP 서버로 등록하면 세션 중 자기 자신에게 쿼리 가능. **read-only 원칙**: 상태 변경은 불가, 추천만 반환한다.

**노출 tool 목록**

- `get_current_bloat()` — 현재 세션 bloat 리포트.
- `get_phase_breakdown()` — 페이즈별 토큰 분포.
- `forecast_compact()` — 예측 결과.
- `diff_sessions(sid_a, sid_b)` — 세션 비교.
- `recommend_action()` — 즉시 적용 가능한 최적화 추천 (텍스트).
- `estimate_budget(task_description)` — 작업 설명을 받아 예상 토큰·tool subset 제안.

**기능 요구사항**

- FR-6.1: stdio transport, `ccprophet mcp` 한 줄로 실행.
- FR-6.2: 각 tool 응답 < 500ms.
- FR-6.3: tool 정의 합계 < 1500 tokens (스스로가 bloat가 되지 않도록).
- FR-6.4: **쓰기 tool 금지** — settings.json 패치·스냅샷 복원 등 상태 변경은 CLI 전용.

### 6.7 F7. Auto Tool Pruning — *killer feature*

bloat 분석의 결과를 **실제 제거 액션으로 자동 변환**한다. 최근 N개 세션의 tool usage 통계를 집계해 "지난 30일 한 번도 안 쓴 MCP 서버"를 `.claude/settings.json` 패치 후보로 제안하고, 사용자가 `--apply`하면 settings.json의 스냅샷을 남긴 뒤 disable 패치를 자동 적용한다.

**작동 방식**

1. `ccprophet prune` — dry-run. 제거 후보 목록과 예상 절감 토큰 출력.
2. `ccprophet prune --apply` — settings.json 자동 패치 + 스냅샷 저장.
3. `ccprophet snapshot list` / `ccprophet snapshot restore <id>` — 원복.

**기능 요구사항**

- FR-7.1: **dry-run이 기본값**. 실제 수정은 명시적 `--apply` 플래그 필수.
- FR-7.2: 제거 후보 선정 기준은 설정 가능 — 기본: 최근 30일·3세션 이상 등장하되 사용률 0%.
- FR-7.3: settings.json 패치 전 timestamp 기반 스냅샷 저장 (`~/.claude-prophet/snapshots/`).
- FR-7.4: Subset 프로필 모드 — 제거 대신 태스크별 subset 프로필(`planning.json`, `refactor.json`)을 생성해 심볼릭 로딩 가능.
- FR-7.5: 권장 사항에 대한 confidence score 제공 (토큰 절감액·미사용 일수 기반).
- FR-7.6: MCP 서버별 `.mcp.json` 패치도 동일 메커니즘으로 지원.

### 6.8 F8. Context Budget Optimizer — *killer feature*

"이 작업은 몇 토큰 쓸까?"에 답하는 **사전(pre-flight) 예측기**. 과거 세션을 작업 유형별(refactor, debug, new-feature, review 등)로 태그하고, 유사 작업의 토큰·phase·tool 사용 패턴을 기반으로 다음 작업의 예상 budget과 권장 tool subset을 제안한다.

**사용 흐름**

```
$ ccprophet budget refactor-auth
estimated tokens: 115k ± 18k  (n=7 similar sessions)
recommended subset: Read, Edit, Grep, Bash  (drop 9 MCPs → save 22k)
expected phases: planning 12%, implementation 65%, review 23%
risk: 2/7 similar sessions hit autocompact — consider /clear at 80k
```

**기능 요구사항**

- FR-8.1: 작업 유형 태그는 `ccprophet tag <SID> <type>` CLI로 수동 부여 (초기). Phase 3에서 자동 분류 실험.
- FR-8.2: 유사 세션 검색은 (작업 유형, 프로젝트, 모델) 튜플 기반. 최소 n=3 이상일 때만 예측 제공, 아니면 "insufficient data" 반환.
- FR-8.3: 예측 결과에는 신뢰구간·샘플 수·risk flag 포함.
- FR-8.4: 추천된 subset은 F7의 subset 프로필로 바로 export 가능 (`--emit-profile refactor.json`).
- FR-8.5: 예측 정확도 MAE ≤ 25% (실 토큰 vs 예측 토큰). 부정확할 때 명시적으로 신뢰도 하향 표시.

### 6.9 F9. Session Replay & Diff — *killer feature*

두 세션(혹은 단일 세션)을 **시간 슬라이더로 되감기**하며 phase·tool·bloat의 진행을 시각화한다. "좋은 세션 vs 나쁜 세션" 비교를 통해 스스로의 작업 패턴을 학습한다.

**핵심 UX**

- Web DAG 뷰와 같은 접점(F4). 좌/우 분할 replay.
- 공통 phase에 시간축을 정렬 (normalized 또는 wall-clock).
- 한쪽에서 bloat가 튀는 지점에 빨간 마커, 사용자가 클릭하면 해당 순간의 tool_calls/file_reads 하이라이트.
- CLI 요약(`ccprophet diff A B`)은 web 없이도 주요 delta 테이블 제공.

**기능 요구사항**

- FR-9.1: Replay는 이미 DuckDB에 저장된 이벤트 기반. 재실행 없음.
- FR-9.2: 세션 A·B 재생 속도 독립 조절. 스크럽 시 좌우 동기화 옵션.
- FR-9.3: "pattern diff" — phase 구성·tool 빈도·bloat 곡선의 Δ를 자동 요약 텍스트로 출력.
- FR-9.4: 세션 북마크 — 사용자가 "이 세션은 성공/실패"로 라벨링 가능, diff 대상 선택에 활용.
- FR-9.5: Export: 비교 결과를 마크다운 리포트로 저장 (`ccprophet diff A B --md out.md`).

### 6.10 F10. Cost Dashboard — *killer feature*

모든 절감·낭비를 **달러(또는 사용자 지정 통화)**로 환산해 표시한다. 토큰 숫자는 추상적이지만 `$52/mo`는 행동을 부른다.

**작동 방식**

- 모델별 요율표를 내장(최신치는 PyPI 업데이트로 갱신). 사용자는 `~/.claude-prophet/pricing.toml`로 override 가능.
- 세션당 `(input_tokens × rate_in) + (output_tokens × rate_out) = session_cost` 계산.
- Pruning 적용 전/후 세션 비교로 **"절약된 달러"**를 실측 노출.
- 월별 롤업: "지난달 $182 사용, 이 중 $47은 미사용 MCP", "현재 pruning 적용 시 예상 월 $52 절약".

**기능 요구사항**

- FR-10.1: 요율표 없이도 세션당 토큰 요약은 제공. pricing 불명 시 "-" 표시.
- FR-10.2: 통화 변환 오프라인(고정 환율 토글). 기본 USD.
- FR-10.3: 모든 분석 명령에 `--cost` 플래그로 $ 열 추가.
- FR-10.4: `ccprophet cost [--month YYYY-MM]` 전용 명령 — 월별 요약 + 절감 기회 포함.
- FR-10.5: 절감액 계산은 **실측(after − before) 우선**, 예측은 별도로 `estimated_savings` 라벨.
- FR-10.6: 요율표와 계산식은 문서에 완전 공개 (블랙박스 요금 금지).

### 6.12 F12. Quality Watch — *killer feature* (anti-downgrade)

**의심**: 동일 모델·동일 옵션인데도 어느 날부터 결과 품질이 떨어진다는 체감이 있다. Anthropic이 조용히 모델 품질을 낮췄는지, 내 사용 패턴이 변했는지 구분할 수 있어야 한다.

**접근**: 매 세션마다 자동으로 수집되는 객관 지표 집합을 **일별 (모델 × 옵션)** 로 집계해 시계열로 남기고, 최근 N일 평균이 직전 베이스라인(기본 30일)보다 통계적으로 유의하게 악화되면 플래그를 띄운다. 사용자가 눈으로 볼 수 있도록 ASCII sparkline으로 렌더한다.

**추적 지표** (대리 변수; 직접 IQ 측정 불가)

| 지표 | 의미 | 하락 방향의 가설 |
|---|---|---|
| `avg_output_tokens_per_session` | 모델이 내놓는 평균 응답량 | 답변 짧아짐 / 포기 |
| `tool_call_success_rate` | tool_call 성공률 | 잘못된 호출 증가 |
| `autocompact_hit_rate` | autocompact 도달 비율 | 맥락 유지 실패 |
| `avg_tool_calls_per_session` | 세션당 평균 tool 호출 수 | 비효율 증가 |
| `repeat_read_rate` | 같은 파일 5회+ re-read 비율 | 이해 부진 (디버깅 루프) |
| `outcome_fail_rate` | 라벨링된 세션 중 fail 비율 | 실제 실패 체감 |
| `input_output_ratio` | input / output 토큰 비율 | 비효율, 모델 장황함 |

**작동 방식**

1. `ccprophet quality` — (모델, task_type 선택) 시계열 테이블 + 각 지표의 ASCII sparkline 렌더.
2. `--window 7d --baseline 30d` — 최근 7일 vs 직전 30일 평균 비교. 평균이 2σ 이상 벗어나면 `[DEGRADED]` 플래그.
3. `--model claude-opus-4-7` — 특정 모델만.
4. JSON 출력은 CI나 외부 대시보드와 연동 가능.

**기능 요구사항**

- FR-12.1: 일별 집계는 기존 `sessions`·`tool_calls`·`outcome_labels` 테이블에서 SQL로 도출. 추가 수집 부담 없음.
- FR-12.2: 각 지표의 표준편차·샘플 수를 응답에 포함. n<3인 window는 "insufficient" 표시.
- FR-12.3: 회귀 임계치 기본값 2σ, `--threshold` 로 조정.
- FR-12.4: 해석 가능성 — 플래그된 지표마다 "왜 의심되는지"를 1줄 설명 동반 (NFR-10).
- FR-12.5: `--since <date>` / `--until <date>` 로 창 이동 가능, 특정 모델 릴리즈 전후 비교 UX.
- FR-12.6: ASCII sparkline은 rich 기반, 고정폭 폰트에서 깨지지 않아야 함.
- FR-12.7: `quality export --parquet` 로 외부 분석 파이프라인 연동.

### 6.13 F11. Session Outcome Engine — *killer feature*

"좋은 결과를 만드는 엔진." 사용자가 세션을 성공/실패로 라벨링하거나 자동 신호(autocompact 미도달, 테스트 통과 등)를 근거로 **성공 세션의 config·phase 패턴을 클러스터링**, 다음 유사 작업 시작 시 "best config" 프로필을 재현한다.

**작동 흐름**

1. **라벨 수집**: `ccprophet mark <SID> --outcome success|fail [--reason ...]` 또는 자동 라벨 규칙(autocompact 도달=부분실패 등).
2. **패턴 학습**: 작업 유형 × 모델 × 프로젝트 클러스터별로 성공 세션의 공통 config/phase 분포를 뽑는다.
3. **재현**: `ccprophet reproduce <task-type>` → "성공 패턴: MCP subset `[...]`, 예상 phase 분포, 권장 시점 `/clear` 82k 부근". `--apply`로 프로필 로드.
4. **실패 분석**: `ccprophet postmortem <SID>` → 유사 성공 세션과 비교해 "어느 지점에서 bloat 폭증, Read-loop, compact 과다"인지 자동 진단.

**기능 요구사항**

- FR-11.1: 라벨은 수동·자동 병행. 자동 규칙은 사용자 커스터마이즈 가능 (`outcome_rules.toml`).
- FR-11.2: 최소 n≥3의 성공 샘플이 있어야 "best config" 권장. 미만이면 insufficient.
- FR-11.3: Outcome engine은 결과 **설명 가능성** 필수 — "왜 이 구성이 성공인지" 1줄 근거.
- FR-11.4: `ccprophet reproduce --apply`는 F7 pruning/subset과 동일하게 snapshot·rollback 연동.
- FR-11.5: 실패 세션 postmortem은 마크다운 export 지원 (회고/팀 공유).

## 7. 비기능 요구사항 (Non-Functional Requirements)

- **NFR-1 성능**: 훅 오버헤드 < 50ms p99, CLI cold start < 500ms, 추천·budget 쿼리 < 1s.
- **NFR-2 보안**: 외부 네트워크 호출 0회가 기본값. OTLP 브리지는 opt-in.
- **NFR-3 프라이버시**: prompt 본문·tool input/output은 기본 redact. `--log-content` 명시 플래그 필요.
- **NFR-4 이식성**: macOS 13+, Ubuntu 22.04+, Windows 11 WSL2.
- **NFR-5 설치 용이성**: `uvx ccprophet` 또는 `pipx install ccprophet` 한 줄. Docker 불필요.
- **NFR-6 용량**: 설치 후 디스크 < 30MB, 30일 사용 후 DB < 500MB, 스냅샷 디렉토리 < 50MB (자동 로테이션).
- **NFR-7 장애 격리**: ccprophet 오류가 Claude Code 세션에 절대 영향 주지 않음 (훅 timeout 10s, silent fail).
- **NFR-8 원복 가능성**: 모든 자동 변경(settings.json/.mcp.json 패치, subset 프로필 적용)은 스냅샷 기반 1-step rollback 지원. 스냅샷 없이 apply 금지.
- **NFR-9 안전 기본값**: pruning·apply 계열 명령은 dry-run이 기본, 파괴적 동작은 명시 플래그(`--apply`, `--force`) 필수. MCP 서버는 read-only 고정.
- **NFR-10 설명 가능성**: 추천 항목은 "왜 이 제안인가"를 1줄 이상으로 표기 (최근 N세션 0회 사용, 토큰 절감 X 등). 블랙박스 추천 금지.
- **NFR-11 금액 투명성**: 토큰 → $ 환산 식과 요율표는 전부 공개. 사용자 override 가능, 네트워크 호출 없이 오프라인 계산.
- **NFR-12 Outcome 신뢰성**: "best config" 추천은 샘플 수·성공 라벨 근거 1줄을 반드시 포함. 블랙박스 "이 config가 더 좋다" 제안 금지.

## 8. 아키텍처 (Architecture)

```
┌──────────────────┐                       ┌──────────────────────┐
│   Claude Code    │                       │   ~/.claude/         │
│   CLI Session    │─── writes JSONL ────▶│   projects/**/*.jsonl│
│                  │                       └──────────┬───────────┘
│   PostToolUse ───┼─┐                               tail
│   Stop Hook ─────┼─┼──▶ ccprophet ingestor ──append──▶│
│   Subagent Stop ─┼─┘      (Python, 50 LOC)          ▼
└──────────────────┘                       ┌──────────────────────┐
                                           │  DuckDB file         │
                                           │  ~/.claude-profiler/ │
                                           │  events.duckdb       │
                                           └─────┬────┬────┬──────┘
                                                 │    │    │
                            ┌────────────────────┘    │    └──────────────────┐
                            ▼                         ▼                       ▼
                   ┌────────────────┐      ┌──────────────────┐     ┌──────────────────┐
                   │ Analyzer CLI   │      │  Web DAG Server  │     │  MCP Server Mode │
                   │ (Rich UI)      │      │  (vanilla JS+D3) │     │  (stdio)         │
                   └────────┬───────┘      └────────┬─────────┘     └────────┬─────────┘
                            ▼                       ▼                        ▼
                      Terminal/statusline      Browser localhost        Claude Code self-
                                                                         introspection
```

**기술 스택**

- 언어: Python 3.10+ (`duckdb`, `rich`, `typer`, `watchdog`, `mcp` SDK).
- 프론트엔드: Vanilla JS + D3.js v7 + Cytoscape.js (단일 HTML).
- 스토리지: DuckDB 1.x (embedded).
- 배포: PyPI (`ccprophet`), optional Homebrew tap.

## 9. 마일스톤 (Phased Roadmap)

> **Principle (v0.4)**: MVP는 **"팔리는 3제품"**으로 좁힌다. 관측성 잡화상이 되지 말고, 각각이 독립적으로 유틸리티인 3개 제품에 집중한다. 각 제품은 **"자동 fix"·"결과 개선"·"$ 절약"** 세 트랙 중 하나에 반드시 속한다.

### Phase 1 — Sellable MVP (4~6주) — 3 products

공통 기반 (F1 Ingestor, F2 Storage, Phase detection v1)은 세 제품이 공유한다.

#### 제품 A. **Bloat Detector + Auto Fix** (F1+F2+F7 기반)
- 미사용 MCP/tool 자동 탐지.
- **settings.json / .mcp.json patch 자동 생성 및 적용** (`prune --apply`).
- 스냅샷·rollback 완비.
- CLI: `bloat`, `recommend`, `prune`, `snapshot`.
- **Exit 조건**: 자기 세션에서 `ccprophet prune --apply` 후 다음 세션 free space +10%p 이상 실측.

#### 제품 B. **Session Optimizer** (F8 budget + F11 outcome + F9 diff)
- 세션 라벨링 + 성공 세션 클러스터링.
- 작업 유형 기반 **best config 재현** (`reproduce --apply`).
- 두 세션 diff 기반 "이렇게 하면 더 좋음" 추천.
- CLI: `mark`, `budget`, `reproduce`, `postmortem`, `diff`.
- **Exit 조건**: 성공 세션 n≥3 클러스터에서 reproduce 적용 시 다음 세션 bloat 또는 autocompact 회피율 개선 실측.

#### 제품 C. **Cost Dashboard** (F10)
- 토큰 → $ 변환, 월별 요약.
- Pruning 적용 전/후 **실측 절약 $** 노출.
- CLI: `cost`, `live --cost`, `bloat --cost`.
- **Exit 조건**: 본인 계정 월별 $ 요약 + "예상 월 $X 절약" 숫자 화면 출력.

**Phase 1 Exit (전체)**: 3제품이 모두 독립적으로 동작하고, 서로 중복 없이 각자 UX가 완결. 하나라도 넘기면 Phase 2로 넘어가지 않는다.

### Phase 2 — Depth & Visualization (3~4주)

- F4 Work DAG 웹뷰 + F9 Session Replay (web UI)
- F3 추가 명령: `phase`, `replay`, `query`, `export`
- Phase detection 휴리스틱 고도화
- Cost Dashboard에 프로젝트별 breakdown 추가

**Exit 조건**: 임의의 두 세션을 replay로 나란히 비교. diff 자동 요약.

### Phase 3 — Intelligence (4~6주)

- F5 Forecasting (ARIMA 또는 경량 모델)
- F6 MCP 서버 모드 (read-only)
- F8 자동 작업 유형 분류 실험
- F11 자동 outcome 라벨링 규칙 엔진
- Cross-worktree 집계 (`ccprophet sessions --all-worktrees`)

**Exit 조건**: autocompact 예측 MAE 3분 이내, budget 예측 MAE ≤ 20%, Claude Code가 MCP로 자기 분석 가능.

### Phase 4 — Ecosystem (미정)

- 다른 에이전트 지원 (Codex, OpenCode) — @ccprophet/codex 서브패키지.
- 팀용 집계 레이어 (optional, separate repo).
- Graphify/axon 같은 코드 KG와의 연동 (엣지 weight 교차 참조).
- Subset 프로필 마켓 (커뮤니티 템플릿).
- 팀 단위 Cost Dashboard (SaaS, 별도 조직).

## 10. 성공 지표 (Success Metrics)

**채택 지표**

- SM-1: 출시 후 3개월 내 GitHub 2k stars, PyPI 월 5k 다운로드.
- SM-2: Claude Code 공식 문서나 awesome list에 1회 이상 레퍼런스.
- SM-3: 활성 기여자 5명 이상.

**효용 지표**

- SM-4: **`ccprophet prune --apply` 실행 후 다음 세션 평균 토큰 10% 이상 감소** (실측 before/after, 설문 아님).
- SM-5: autocompact forecast 정확도 MAE ≤ 3분.
- SM-6: 세션당 훅 오버헤드 p99 < 50ms.
- SM-10: **추천 수락률**: `recommend` 결과 중 사용자가 1건 이상 apply한 세션 비율 ≥ 40%.
- SM-11: **Budget 예측 정확도**: 작업 유형 태그가 있는 세션 대상 MAE ≤ 25%.
- SM-12: **Rollback 안전성**: `snapshot restore` 호출 시 100% 원복 성공 (시뮬레이션 테스트로 검증).
- SM-13: **$ 절약 실측**: `prune --apply` 사용자의 월 평균 절약액 $20 이상 (Claude Opus 기준 pricing 적용). 대시보드에 자기 숫자로 표시됨.
- SM-14: **Outcome 재현율**: `reproduce --apply` 적용 세션의 bloat 중위값이 미적용 대조군보다 30% 이상 낮음.
- SM-15: **Postmortem 유용성**: 실패 라벨 세션의 postmortem이 "성공 패턴과의 Δ ≥ 2건"을 제시하는 비율 ≥ 70%.

**품질 지표**

- SM-7: 이슈 close median time < 7일.
- SM-8: CI 커버리지 > 80%.
- SM-9: 설치부터 **첫 추천(prune dry-run)** 까지 소요 시간 중앙값 < 3분.

## 11. 리스크 및 대응 (Risks & Mitigations)

| 리스크 | 영향 | 대응 |
|---|---|---|
| Anthropic이 `/context`에 효율 분석 기능을 내장 | 차별화 희석 | 액션·rollback·budget 예측 같은 **행동 계층**은 Anthropic이 흡수하기 어려움. 이 계층에 투자 집중. |
| JSONL 포맷 변경 | Ingestor 파손 | 스키마 버전 감지 + 실패 시 silent degrade, 스키마 adapter 레이어 분리 |
| DuckDB 파일 손상 | 히스토리 유실 | 일별 Parquet snapshot 자동 백업, `ccprophet doctor` 복구 명령 |
| 훅 오버헤드로 Claude Code UX 저하 | 치명적 | Timeout 10s + try/except + silent fail, 성능 회귀 테스트 |
| Phase detection 휴리스틱 오류 | 사용자 신뢰 저하 | 초기에는 "Phase detection (beta)" 라벨, 수동 override CLI 제공 |
| **Auto Pruning 오적용** (실제 필요한 MCP를 disable) | 사용자 작업 중단 | dry-run 기본, `--apply` 필수, 스냅샷 기반 1-step rollback, 직전 30일 사용 이력을 confidence로 노출 |
| **Budget 예측 과신** | 사용자 오판 유도 | 신뢰구간·샘플 수·risk flag 병기 필수, n<3이면 예측 비활성 |
| settings.json을 외부 도구(editor, 다른 CLI)가 동시 편집 | 패치 충돌 | 원자적 write + etag/hash 비교, 충돌 시 apply 중단 |
| 오픈소스 단일 메인테이너 burnout | 장기 지속성 | 처음부터 모듈 분리 (ingestor/analyzer/viz/recommender 별도 패키지화), 기여 가이드 문서화 |

## 12. 오픈 퀘스천 (Open Questions)

- Q1: OTLP 브리지를 기본 ON으로 할지 OFF로 할지? (현재 제안: OFF, opt-in)
- Q2: DuckDB 대신 SQLite를 기본으로 할지? (현재 제안: DuckDB, 쿼리 성능 우위)
- Q3: Phase 4의 다른 에이전트 지원을 이 레포에서 할지, fork 허용할지?
- Q4: 유료 tier 가능성? (현재 제안: 전면 오픈소스, SaaS 레이어는 별도 조직이 만들도록)
- Q5: 한국 공공기관·KCMVP 호환 bundle을 별도 릴리즈로 낼지?
- Q6: `prune --apply`를 interactive confirmation prompt까지 요구할지, `--yes` 단일 플래그로 일괄 수락할지? (현재 제안: interactive 기본, CI 자동화용 `--yes`)
- Q7: Budget 예측의 작업 유형을 사용자 수동 태그(`ccprophet tag`)로 받을지, 프로젝트별 기본 태그를 프롬프트 기반으로 자동 분류할지? (현재 제안: Phase 2 수동, Phase 3 실험적 자동 분류)
- Q8: Subset 프로필을 Claude Code의 settings.json `disabled` 필드로 표현할지, 별도 ccprophet 전용 프로필 파일로 둘지? (전자는 즉시 반영, 후자는 ccprophet 활성 상태에서만 적용)
- Q9: Pricing 기준을 고정 요율표(PyPI 업데이트)로 할지, `/stats` 등에서 실측 요율을 끌어올지? (현재 제안: 내장 요율표 + 사용자 override, 네트워크 호출 금지)
- Q10: Outcome 자동 라벨링 규칙의 기본 세트 — autocompact 도달, 에러 메시지 등장, 동일 파일 재편집 횟수 등 중 어디까지를 "실패"로 볼지? (현재 제안: 규칙 엔진 + 사용자 튜닝, 기본값은 autocompact-hit + 사용자 수동만)
- Q11: Outcome engine의 "재현"이 실제로 config를 apply까지 하는 게 맞는지, 읽기 전용 권고로 둘지? (현재 제안: apply는 opt-in, 기본은 권고)

## 13. 부록 (Appendix)

### A. 참고 프로젝트

- `ryoppippi/ccusage` — 로컬 JSONL 기반 사용량 리포트의 레퍼런스
- `Maciek-roboblog/Claude-Code-Usage-Monitor` — Rich UI 터미널의 레퍼런스
- `disler/claude-code-hooks-multi-agent-observability` — 훅 기반 이벤트 스트리밍의 레퍼런스
- `patoles/agent-flow` — canvas 시각화의 레퍼런스
- Claude Code 공식 Monitoring docs — OpenTelemetry 스키마

### B. 용어 정의

- **Bloat**: 컨텍스트에 로딩되었으나 세션 종료까지 호출·참조되지 않은 tool 정의, 파일, MCP 서버.
- **Phase**: 하나의 "작업 단위" (예: Planning, Implementation, Review). Task tool 호출 또는 사용자 prompt 경계로 분리.
- **Loaded vs Referenced**: 컨텍스트에 존재한 아이템 수 vs 실제 tool_use/assistant 응답에서 참조된 아이템 수의 비율.
- **Autocompact**: Claude Code가 컨텍스트 한도 근처에서 대화 요약을 트리거하는 이벤트.
- **Recommendation**: 사용자가 즉시 적용 가능한 최적화 제안. 종류: `prune_tool`, `disable_mcp`, `run_clear`, `switch_subset`, `compact_focus`.
- **Pruning**: 미사용 MCP/tool을 settings.json에서 비활성화하는 액션. 반드시 스냅샷과 페어링.
- **Snapshot**: 자동 변경 직전의 settings/.mcp 파일 전체 복사본. timestamp + reason(태그)으로 식별, `snapshot restore`로 원복.
- **Subset Profile**: 특정 작업 유형용 최소 tool/MCP 집합 정의. 예: `refactor.json`, `review.json`.
- **Budget Envelope**: 과거 유사 세션 기반으로 산출된 예상 토큰 범위(평균 ± 신뢰구간) + 권장 subset.
- **Confidence**: 추천·예측에 부여되는 0.0~1.0 값. 샘플 수, 최근성, 편차 기반.
- **Cost Model**: 모델별 (input_per_M, output_per_M) 요율 테이블. 오프라인, 사용자 override 가능.
- **Session Cost**: `(input_tokens * rate_in) + (output_tokens * rate_out)`. USD 기본.
- **Estimated Savings**: 예측치 절약액. 실측(`realized_savings`)과 구분 라벨링.
- **Outcome Label**: `success`·`fail`·`partial` 중 하나. 수동 또는 규칙 엔진에서 부여.
- **Best Config**: 성공 라벨 세션 클러스터로부터 도출된 MCP/tool subset·phase 구성 프로필.
- **Postmortem**: 실패 세션과 유사 성공 세션의 구조적 Δ 자동 리포트.

### C. 데모 시나리오

**시나리오 1 — Auto Pruning (F7)**
사용자가 12개 MCP 서버를 붙인 채 세션 종료. `ccprophet recommend` → 최근 30일 통계 기반 "mcp__github·mcp__jira 등 9개 서버 0회 사용, 제거 시 18k 절감 (신뢰도 0.92)". `ccprophet prune --apply` 실행 → settings.json 스냅샷 저장 후 자동 patch → 다음 세션 `/context` 에서 free space +9%p 실측. 필요 시 `ccprophet snapshot restore <id>` 원클릭 원복.

**시나리오 2 — Budget 사전 예측 (F8)**
사용자가 리팩토링 작업 시작 전 `ccprophet budget refactor-auth` 실행 → "유사 세션 7건 기준 평균 115k ± 18k, MCP subset `[Read, Edit, Grep, Bash]` 권장 (22k 절감), 2/7은 autocompact 도달 — 80k 시점 `/clear` 권장". `--emit-profile refactor.json` 추가로 subset 프로필 저장 후 다음 세션에 로드.

**시나리오 3 — Session Replay & Diff (F9)**
같은 모듈 리팩토링을 이틀에 걸쳐 두 번 수행. 첫날 bloat 35% / 두 번째날 12%. `ccprophet replay SID1 --compare SID2` → 웹뷰에서 좌우 분할 replay, phase 구성 비교. 자동 delta 텍스트: "Day2는 Task 호출 0회 (vs Day1 3회), Edit 비율 2배, subset 프로필 적용으로 MCP 22k 절감". 사용자가 이 diff를 마크다운으로 export하여 회고 문서화.

**시나리오 4 — Claude Code 자기 분석 (F6)**
세션 중 사용자가 "지금 내 세션 효율 어때?" 질문. Claude Code가 `ccprophet mcp`를 호출해 `recommend_action()` → "MCP 5개 사용률 0%, 제거 시 12% 확보. `ccprophet prune --apply` 실행 권장" 텍스트 응답. 사용자는 CLI에서 실제 pruning을 수행 (MCP는 read-only라 직접 변경 불가).

**시나리오 5 — Cost Dashboard (F10)**
월초 회고차 `ccprophet cost --month 2026-03` 실행 → "3월 Claude Opus $182 사용 (in 2.1M / out 0.4M tokens). 미사용 MCP 기여 $47. 현재 settings로 4월 예상 월 $52 절약 가능." 출력. 사용자가 `ccprophet prune --apply` 후 4월 말 같은 명령으로 실측 절약액 확인.

**시나리오 6 — Outcome Engine (F11)**
같은 리팩토링 작업을 A/B 두 번 수행. 세션 A는 막판 autocompact 도달(`ccprophet mark A --outcome fail`), 세션 B는 깔끔 종료(`mark B --outcome success`). `ccprophet reproduce refactor-auth` → "3건 성공 세션 기준 best config: MCP `[Read,Edit,Grep,Bash]`, Planning 15% 이하 유지, 80k 시점 `/clear` 권장 (confidence 0.81)". `--apply`로 subset 프로필 로드 후 세 번째 세션은 성공.

**시나리오 7.5 — Quality Watch (F12)**
사용자가 "요새 Claude가 멍청해진 것 같다" 의심. `ccprophet quality --model claude-opus-4-7 --window 7d --baseline 30d` 실행 → "7일 평균 output_tokens 1,240 (baseline 2,010), -38%, 2.3σ — **[DEGRADED]**. tool_call_success_rate도 0.91 → 0.78로 유의미 하락." 시계열 sparkline과 함께 출력. 사용자가 해당 기간의 세션을 샘플링해 품질 저하 여부 직접 확인·SNS 공유.

**시나리오 8 — Postmortem (F11)**
실패 세션 `ccprophet postmortem <SID>` → "유사 성공 세션 5건과 비교: (1) Task tool 호출 4회 초과, (2) 동일 파일 7회 re-read, (3) MCP subset에 불필요한 `mcp__github` 포함. 개선 제안: subset profile `refactor.json` 적용 + CLAUDE.md에 해당 모듈 요약 추가." 사용자가 마크다운 export로 팀 회고 문서화.

---

**문서 종료**
