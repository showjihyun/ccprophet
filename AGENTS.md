# AGENTS.md

`ccprophet` 저장소에서 작업하는 **모든 AI 에이전트** (Claude Code, Cursor, Aider, Codex, OpenCode 등)가 반드시 준수해야 하는 공통 규칙이다. 에이전트 종류에 무관하게 적용된다.

`CLAUDE.md`가 "이 프로젝트가 무엇인가"라면, 본 문서는 "작업할 때 어떻게 행동해야 하는가"를 규정한다.

---

## 0. 요약 (Must-Follow Rules)

1. **Python 패키지 관리는 오직 `uv`만 사용한다. `pip` 사용 금지.**
2. **계층 의존성 방향을 위반하지 않는다.** `harness → adapters → {use_cases, ports} → domain` 한 방향. `docs/LAYERING.md` §2·§5 참조. (§3에 요약)
3. 보안·프라이버시 원칙(로컬 전용, redact 기본 ON)은 타협 불가.
4. 스키마·아키텍처·계층 변경은 `docs/` 업데이트와 동시 커밋.
5. 커맨드 실행 전 `CLAUDE.md`의 "금지 사항"을 한 번 더 확인한다.
6. 외부 네트워크 호출·파일 쓰기·MCP 서버 수정 같은 **영향 범위가 큰 작업은 사용자 확인 후 실행**.

---

## 1. Python 패키지 관리 — **반드시 `uv` 사용**

### 1.1 절대 규칙

ccprophet의 모든 Python 패키지 관리는 [astral-sh/uv](https://github.com/astral-sh/uv)로만 수행한다. `pip`, `pip-tools`, `poetry`, `pipenv`, `conda` 등 다른 도구는 **사용 금지**.

**이유**
- `uv`는 `pip`보다 10~100배 빠르고, lock 파일(`uv.lock`)로 재현 가능한 환경을 보장한다.
- `pyproject.toml` + `uv.lock` 조합으로 dev/prod 의존성을 한 파일에 관리 (Python 표준 PEP 621).
- ccprophet의 NFR-1(cold start < 500ms)과 설치 경로(`uv tool install ccprophet`) 일관성.

### 1.2 금지 명령

다음 명령을 제안·실행·문서화 하지 않는다:

```bash
# ❌ 금지
pip install …
pip install -r requirements.txt
python -m pip install …
python setup.py install
python setup.py develop
poetry add …
pipenv install …
conda install …
easy_install …
```

`requirements.txt` / `setup.py` / `Pipfile` / `poetry.lock` / `environment.yml` 같은 파일도 새로 만들지 않는다. 이미 존재하면 `pyproject.toml`과 `uv.lock`으로 마이그레이션 제안.

### 1.3 허용 명령 (대응표)

| 목적 | ❌ pip/poetry | ✅ uv |
|---|---|---|
| 환경 동기화 | `pip install -r requirements.txt` | `uv sync` |
| 런타임 의존성 추가 | `pip install duckdb` | `uv add duckdb` |
| 개발 의존성 추가 | `pip install -D pytest` | `uv add --dev pytest` |
| 제거 | `pip uninstall duckdb` | `uv remove duckdb` |
| 버전 고정 | `pip freeze > requirements.txt` | `uv lock` |
| 스크립트 실행 | `python -m ccprophet` | `uv run ccprophet` |
| 테스트 실행 | `pytest` | `uv run pytest` |
| 도구 실행 (일회성) | `pipx run …` | `uvx …` |
| 전역 설치 | `pipx install ccprophet` | `uv tool install ccprophet` |
| Python 버전 | `pyenv install 3.12` | `uv python install 3.12` |
| 가상환경 생성 | `python -m venv .venv` | `uv venv` |

### 1.4 CI / 문서에서도 동일

- GitHub Actions·pre-commit·Docker 이미지 어디서든 `pip` 명령어가 등장하면 **교체 또는 제거**.
- `README.md`·`CONTRIBUTING.md`·docstring 예시에도 `pip install` 문구 금지.
- 사용자에게 설치를 안내할 때도 `pip install ccprophet` 제안 금지. `uv tool install ccprophet` 또는 `uvx ccprophet`.

### 1.5 예외

사용자가 명시적으로 `pip`를 요구하고 그 이유가 타당한 경우(레거시 CI, 특정 배포 환경)에 한해, 해당 파일·맥락에 **주석으로 이유를 명시**하고 진행한다. 이 예외는 해당 파일 scope 한정이며, 다른 파일로 확산 금지.

---

## 1A. 계층 의존성 규칙 — **Clean Architecture + Hexagonal**

권위 문서: `docs/LAYERING.md`. 본 섹션은 에이전트 관점의 요약.

### 1A.1 의존성 방향

```
harness  →  adapters  →  { use_cases, ports }  →  domain
```

안쪽(`domain`)이 바깥쪽 이름을 알면 안 된다. `import` 한 방향.

### 1A.2 계층별 import 규칙

| 계층 | 허용 import | 금지 import |
|---|---|---|
| `domain/` | stdlib + `dataclasses`·`typing`·`datetime`·`uuid`·`hashlib`·`enum` | third-party 일체 |
| `use_cases/` | `domain/`, `ports/` | third-party, `adapters/`, `harness/` |
| `ports/` | `domain/`, `typing.Protocol` | third-party, `use_cases/`, `adapters/`, `harness/` |
| `adapters/<family>/` | `ports/`, `domain/`, 해당 family의 third-party | 다른 family adapter, `harness/` |
| `harness/` | 모두 | 비즈니스 로직(if/else·for 분기) |

**금지 third-party (domain/use_cases/ports 관점)**: `duckdb`, `fastapi`, `starlette`, `typer`, `click`, `rich`, `watchdog`, `mcp`, `statsmodels`, `httpx`, `requests`, `urllib3`, `sqlalchemy` 등.

### 1A.3 Port 설계 규칙

- Port는 **안쪽 계층이 정의**한다 (Repository 인터페이스는 `ports/`, 구현은 `adapters/`).
- 기본은 `typing.Protocol` (구조적 타입). `abc.ABC`는 기본 구현 공유가 필요할 때만.
- Use Case 생성자는 **Protocol 타입만** 받는다. 구체 클래스·커넥션을 직접 받지 않는다.
  ```python
  # ❌ 금지
  def __init__(self, conn: duckdb.DuckDBPyConnection): ...
  # ✅ OK
  def __init__(self, sessions: SessionRepository): ...
  ```

### 1A.4 Driving vs Driven

- **Driving (inbound)**: CLI, Web, MCP, Hook receiver. 외부 호출을 Use Case 호출로 변환.
- **Driven (outbound)**: Repository, Clock, Redactor, Logger, ForecastModel, FileWatcher, Publisher. Use Case가 의존하는 외부 세계.

새 IO가 필요하면 **먼저 Port를 정의**하고 Adapter를 구현한다. Use Case에 직접 박지 않는다.

### 1A.5 테스트 파트너

- **Repository Port마다 InMemory Fake를 `adapters/persistence/inmemory/`에 유지**. Fake는 DuckDB 어댑터와 동일한 **Contract 테스트**(`tests/contract/`)를 통과해야 한다.
- Use Case unit test는 InMemory Fake를 주입해 작성한다. Mock은 최후의 수단.
- Clock은 `SystemClock`/`FrozenClock` 2개 어댑터 유지. 테스트에서 `time.sleep` 금지.

### 1A.6 정적 검증

```bash
uv run lint-imports      # import-linter: 계층·금지 모듈·adapter 간 독립성 검증
```

PR이 계약을 깨뜨리면 CI 거절. 새 계약 추가는 `pyproject.toml`의 `[tool.importlinter]`에 반영.

### 1A.7 Anti-pattern 빠른 참조

| 패턴 | 문제 | 대체 |
|---|---|---|
| Use Case가 `duckdb.connect()` 직접 호출 | LP-5 위반 | Repository Port 주입 |
| Domain entity가 ORM 모델 상속 | 영속 결합 | dataclass + adapter 매핑 |
| Adapter A가 Adapter B import | 교차 결합 | Port 경유 또는 harness 조립 |
| Harness에 비즈니스 if/else | composition root 오염 | Use Case로 이동 |
| Repository를 `Mock`으로 스텁 | 교체 시 재작성 | InMemory Fake + Contract 테스트 |
| SQL 안에 Phase 판정 로직 | 재사용·테스트 곤란 | `domain/services/phase.py`로 추출 |
| `datetime.now()` 직접 호출 | flaky 테스트 | Clock Port 주입 |

---

## 2. 명령 실행 규칙

### 2.1 안전하게 실행 가능 (사용자 확인 불필요)

- `uv sync`, `uv run <test/lint/typecheck>`, `uv lock`, `uv add --dry-run`
- 읽기 전용 분석 (`ccprophet bloat`, `ccprophet query`)
- `git status`, `git diff`, `git log`

### 2.2 확인 후 실행 (사용자 승인 필요)

- `uv add <package>` — 의존성 그래프 변경
- `uv remove <package>` — 기능 제거 가능성
- `ccprophet install` — `.claude/settings.json` 쓰기
- 마이그레이션 실행 — DuckDB 스키마 변경
- `git push`, `git commit`, PR 생성, 이슈 close
- 외부 네트워크 호출 (OTLP bridge ON 등)

### 2.3 사용자 지시 없이는 절대 금지

- `git push --force`
- `rm -rf`, `git reset --hard`, `git clean -fd`
- DuckDB 파일 삭제 (`~/.claude-prophet/events.duckdb`)
- `.claude/settings.json`의 기존 훅 덮어쓰기 (병합은 OK)
- MCP 서버 등록 해제·변경
- `uv.lock` 수동 편집

---

## 3. 코드 수정 행동 지침

### 3.1 변경 범위 최소화

- 요청된 작업에 필요한 파일만 수정. 주변 "청소" 금지.
- 기존 스타일·네이밍·패턴을 그대로 따른다. 리팩토링은 별도 PR.
- 3회 이상 반복되는 패턴만 추상화. 추측성 범용 API 금지.

### 3.2 문서 동기화 의무

| 변경 | 동시 업데이트 |
|---|---|
| 테이블·컬럼·인덱스 | `docs/DATAMODELING.md`, `migrations/V*.sql` |
| 새 컴포넌트·계층 | `docs/ARCHITECT.md` |
| 새 기능·CLI 명령 | `docs/PRD.md` (기능 목록), `README.md` |
| UI 토큰·컴포넌트 | `docs/DESIGN.md` |
| 새 훅·환경변수·설정 | `CLAUDE.md`, `AGENTS.md` |

문서 업데이트가 누락된 PR은 리뷰어가 거절한다.

### 3.3 테스트 요구

- 새 public 함수·CLI 명령·SQL 쿼리에는 테스트 동반.
- 버그 수정은 regression test 없이 머지 불가.
- 훅 경로 수정 시 `tests/perf/test_hook_latency.py` p99 검증 실행.

### 3.4 주석 정책

- 기본값: **주석 없음**. 좋은 네이밍·타입이 대체.
- 예외적으로 작성할 때는 **왜**(WHY)만 쓴다. 무엇(WHAT)은 코드가 말한다.
- 이슈 번호·PR 번호 주석 금지 (`# fix for #123`). git blame이 담당.

---

## 4. 데이터 안전 규칙

### 4.1 저장소 파일

- `~/.claude-prophet/events.duckdb` — 메인 DB. 삭제·잘라내기 금지.
- `~/.claude-prophet/checkpoint.json` — 재시작 시 중복 ingest 방지. 수동 편집 금지.
- `~/.claude-prophet/archive/*.parquet` — 일별 아카이브. 에이전트가 함부로 삭제하지 않는다.
- `~/.claude/projects/**/*.jsonl` — Claude Code 원본. **읽기 전용**. 어떤 경우에도 수정·삭제 금지.

### 4.2 Redaction

- 신규 코드가 `file_path`, `user_prompt.content`, `command_args`를 저장한다면 **반드시 redact 경로 경유**.
- Plain text로 저장하려면 `config.toml`의 opt-in 플래그 검사 코드 필수.

### 4.3 네트워크

- 기본값 offline. `httpx`, `requests`, `urllib` import가 새로 생기면 설계 리뷰 필수.
- `CCPROPHET_OFFLINE=1` 환경변수에서 no-op 경로를 반드시 제공.

---

## 5. UI 렌더링 (CLI / Web / DAG)

- CLI 색·스타일은 `docs/DESIGN.md` §6의 Rich theme 사용. 하드코딩 금지.
- Web은 `docs/DESIGN.md` §3의 CSS 변수만 참조. 인라인 스타일 최소화.
- 빌드 도구(Vite/Webpack/Rollup) 도입 제안 금지 (AP-4).
- 이모지 사용 최소 — CLI는 5종(`✓ ✕ → · ⚡`), Web은 Lucide 아이콘.

---

## 6. 에이전트 간 차이 조정

### 6.1 Claude Code

- `CLAUDE.md` 자동 로드. `docs/` 문서는 필요 시 `@docs/PRD.md`로 첨부.
- MCP 서버로 `ccprophet`이 등록되어 있으면 `get_current_bloat()` 등을 호출해 self-introspection 가능.
- Task tool/서브에이전트 사용 시 `docs/DATAMODELING.md`의 `subagents` 테이블 구조를 의식.

### 6.2 기타 에이전트 (Cursor, Aider, Codex, OpenCode)

- 본 파일(`AGENTS.md`)을 세션 시작 시 반드시 읽는다.
- `CLAUDE.md`도 참고 (Claude 전용 아닌 공통 정보 포함).
- `docs/ARCHITECT.md` §10.2의 adapter pattern은 이 에이전트들의 이벤트 포맷 대응 시 확장점.

### 6.3 Codex·OpenCode 지원 (Phase 4 예정)

- 현재는 1차 대상 아님. `ccprophet/adapters/` 하위에 별도 모듈로 추가.
- 기존 `claude_code.py` adapter에 분기 추가 금지.

---

## 7. 문제 상황별 기본 반응

| 상황 | 에이전트 행동 |
|---|---|
| `uv` 미설치 환경 | `pip` 우회 금지. 사용자에게 `curl -LsSf https://astral.sh/uv/install.sh` 안내 |
| `uv.lock` 충돌 | 자동 해결 금지. 사용자에게 보고 후 `uv lock --upgrade-package <pkg>` 제안 |
| 스키마 마이그레이션 실패 | 자동 롤백만 수행(`BEGIN/ROLLBACK`). 데이터 삭제·DROP 금지 |
| DuckDB 파일 잠금 | 다른 프로세스 탐지·안내. 강제 해제 금지 |
| 테스트 타임아웃 | 코드 수정 전 원인 조사. 타임아웃 상수 임의 증가 금지 |
| Pre-commit hook 실패 | 우회(`--no-verify`) 금지. 원인 수정 후 재커밋 |
| 새 의존성 제안 | 기존 스택으로 대체 가능한지 먼저 검토 (duckdb/rich/typer/fastapi/watchdog) |

---

## 8. 체크리스트 (PR 전)

아래 항목을 모두 확인한 뒤 PR을 올린다.

- [ ] `pip`·`poetry`·`pipenv`·`conda` 명령 없음
- [ ] `requirements.txt`·`setup.py`·`Pipfile` 신규 파일 없음
- [ ] `uv sync && uv run pytest` 통과
- [ ] `uv run ruff check` · `uv run ruff format --check` · `uv run mypy` 통과
- [ ] **`uv run lint-imports` 통과** (Clean Architecture 계층 계약)
- [ ] **`domain/`·`use_cases/`·`ports/`에 third-party import 없음**
- [ ] **신규 IO는 Port 정의 → Adapter 구현 → Contract 테스트 순서로 추가됨**
- [ ] **Repository 신규 구현 시 `tests/contract/` 의 계약 테스트 상속**
- [ ] 스키마 변경 시 `docs/DATAMODELING.md` 업데이트 + 마이그레이션 파일
- [ ] 계층 구조·테스트 전략 변경 시 `docs/LAYERING.md` 업데이트
- [ ] 신규 기능 시 `docs/PRD.md` 기능 표 업데이트
- [ ] UI 변경 시 `docs/DESIGN.md` 토큰·컴포넌트 반영
- [ ] 외부 네트워크 호출 추가되지 않았거나 `CCPROPHET_OFFLINE=1`에서 no-op
- [ ] 민감 정보 redact 경로 경유
- [ ] 훅 수정 시 p99 < 50ms 유지 (tests/perf/test_hook_latency.py)
- [ ] 계층별 커버리지: domain ≥95%, use_cases ≥90%, adapters ≥80%

---

**이 문서의 규칙은 `docs/PRD.md`·`docs/ARCHITECT.md`의 상위 원칙을 운영 단위로 번역한 것이다. 상위 문서와 충돌할 경우 상위 문서를 먼저 수정하고 본 문서를 동기화한다.**
