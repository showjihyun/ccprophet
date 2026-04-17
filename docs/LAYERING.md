# ccprophet — Layered Architecture & Testing

**계층 아키텍처·의존성 방향·테스트 설계서 (LAYERING)**

| 항목 | 내용 |
|---|---|
| 문서 버전 | 0.2 (Sellable MVP Alignment) |
| 작성일 | 2026-04-17 |
| 상위 문서 | `PRD.md` v0.4, `ARCHITECT.md` v0.3 |
| 대상 독자 | 컨트리뷰터, 코드 리뷰어, 테스트 담당 |
| 기조 | **Clean Architecture**(Robert C. Martin) 중심 + **Hexagonal Architecture**(Alistair Cockburn)의 Ports & Adapters를 경계 명세 언어로 결합 |

---

## 1. 문서 목적

ccprophet의 코드 구조를 **Clean Architecture의 의존성 규칙(Dependency Rule)** 위에 세우고, **Hexagonal의 Port/Adapter 어휘**로 그 경계에 무엇이 들어갈지 물리적으로 규정한다. 테스트 전략 역시 이 계층 모델에서 파생된다.

두 접근의 관계:

- **Clean Architecture** → **왜** 의존이 안쪽으로만 흘러야 하는가 (계층·동심원·Dependency Rule).
- **Hexagonal (Ports & Adapters)** → **무엇을** 그 경계에 두어야 하는가 (Port 인터페이스 + Driving/Driven Adapter).

Clean이 프레임(동심원)을, Hexagonal이 인터페이스(육각형의 변)를 제공한다. ccprophet은 두 언어를 같이 쓴다.

## 2. 레이어링 원칙 (Layering Principles)

**LP-1. Dependency Rule (Clean Arch 제1원칙)**
의존성은 **바깥 → 안** 한 방향. 안쪽 계층은 바깥쪽 이름조차 알면 안 된다. Python import 기준:
- `domain` → 아무것도 import 안 함 (stdlib만).
- `use_cases` → `domain`, `ports`만.
- `ports` → `domain`만.
- `adapters` → `ports`, `domain` (use case 선택적).
- `harness` → 모두 import 가능 (조립 책임).

**LP-2. Ports are owned by the inside**
인터페이스(Port)는 **안쪽 계층이 정의**하고 **바깥쪽이 구현**한다. `EventRepository` 프로토콜은 `ports/`에, `DuckDBEventRepository` 구현은 `adapters/`에.

**LP-3. Driving vs Driven (Hexagonal)**
- **Driving Port (inbound/primary)**: 외부가 앱을 호출하는 입구. Use Case 자체가 driving port.
- **Driven Port (outbound/secondary)**: 앱이 외부를 호출할 때 쓰는 출구. Repository, Clock, Redactor 등.

**LP-4. Adapters are replaceable**
같은 Port를 만족하는 여러 Adapter가 공존할 수 있다. `InMemoryEventRepository`(테스트)·`DuckDBEventRepository`(prod)가 동일 Port를 만족.

**LP-5. Frameworks live only in Adapters**
`duckdb`·`fastapi`·`typer`·`rich`·`watchdog`·`mcp`·`statsmodels`·`httpx` 등 third-party는 **오직 `adapters/`·`harness/`에서만** import. `domain`·`use_cases`·`ports`는 순수 Python + `dataclasses`·`typing`·`datetime`·`uuid`·`hashlib`만.

**LP-6. Harness = Composition Root only**
`harness/`는 비즈니스 로직을 포함하지 않는다. Adapter를 인스턴스화해 Use Case에 주입하는 조립기 역할만.

**LP-7. 테스트는 계층을 따른다**
계층마다 테스트 종류·속도·도구가 다르다. §7 참조.

## 3. 통합 계층 모델 (Clean + Hexagonal)

```
                    ┌─────────────────────────────────────────────┐
                    │                 Harness                     │
                    │     CLI main · Web server · MCP server      │
                    │          · Hook receiver main               │
                    └───────────────┬─────────────────────────────┘
                                    │ instantiates adapters,
                                    │ injects into use cases
                                    ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                    Driving Adapters (inbound)               │
    │   typer CLI │ FastAPI HTTP │ MCP stdio │ Hook stdin reader  │
    └───────────────┬─────────────────────────────────────────────┘
                    │ calls
                    ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                    Driving Ports                            │
    │                (Use Case interfaces)                        │
    │   IngestEvent · AnalyzeBloat · DetectPhases · ForecastCompact│
    │   RecommendAction · DiffSessions · BackfillFromJsonl        │
    └───────────────┬─────────────────────────────────────────────┘
                    │ implements
                    ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                  APPLICATION CORE                           │
    │                                                             │
    │   ┌───────────────────────────────────────────────────┐     │
    │   │               Use Cases (application)             │     │
    │   │   IngestEventUseCase · AnalyzeBloatUseCase · ...  │     │
    │   └───────────────────────┬───────────────────────────┘     │
    │                           │ uses                            │
    │                           ▼                                 │
    │   ┌───────────────────────────────────────────────────┐     │
    │   │              Domain (enterprise)                  │     │
    │   │   Entities: Session, Event, ToolCall, ToolDef,    │     │
    │   │     FileAccess, Phase, Forecast, Recommendation,  │     │
    │   │     Snapshot, OutcomeLabel, BestConfig,           │     │
    │   │     PostmortemReport, CostBreakdown, PricingRate  │     │
    │   │   Values:   SessionId, TokenCount, BloatRatio,    │     │
    │   │     PhaseType, ToolSource, Money, SnapshotId,     │     │
    │   │     RecommendationKind, OutcomeLabelValue         │     │
    │   │   Services: BloatCalculator, PhaseDetector,       │     │
    │   │     TokenUtilization, Recommender, CostCalculator,│     │
    │   │     OutcomeClassifier, SessionClusterer,          │     │
    │   │     PostmortemAnalyzer, SettingsPatcher(pure)     │     │
    │   └───────────────────────────────────────────────────┘     │
    └─────────────────────────┬───────────────────────────────────┘
                              │ depends on (abstract)
                              ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                    Driven Ports (outbound)                  │
    │   EventRepository · SessionRepository · ToolCallRepository  │
    │   ToolDefRepository · FileReadRepository · PhaseRepository  │
    │   ForecastRepository · RecommendationRepository ·           │
    │   SnapshotRepository · OutcomeRepository · PricingProvider  │
    │   SettingsStore · SubsetProfileStore · OutcomeRulesProvider │
    │   Clock · Redactor · Logger · EventPublisher · FileWatcher  │
    │   ForecastModel                                             │
    └─────────────────────────┬───────────────────────────────────┘
                              ▲ implements
                              │
    ┌─────────────────────────────────────────────────────────────┐
    │                    Driven Adapters                          │
    │   DuckDBEventRepository · DuckDBSessionRepository · ...     │
    │   DuckDBRecommendationRepo · DuckDBOutcomeRepo · ...        │
    │   InMemory* (test)                                          │
    │   JsonFileSettingsStore (atomic) · FilesystemSnapshotStore  │
    │   BundledPricingProvider · TomlOverridePricingProvider      │
    │   TomlOutcomeRulesProvider                                  │
    │   SHA256Redactor · SystemClock · FrozenClock (test)         │
    │   LinearForecastModel · ArimaForecastModel                  │
    │   WatchdogTailer · UnixSocketPublisher · RichLogger         │
    └─────────────────────────────────────────────────────────────┘
```

동심원 뷰로 보면:

```
         ┌──────────────────────────────────────────────────┐
         │               Harness (composition root)         │
         │  ┌──────────────────────────────────────────┐    │
         │  │          Driving + Driven Adapters       │    │
         │  │  ┌────────────────────────────────┐      │    │
         │  │  │      Driving + Driven Ports    │      │    │
         │  │  │  ┌──────────────────────┐      │      │    │
         │  │  │  │     Use Cases        │      │      │    │
         │  │  │  │  ┌──────────────┐    │      │      │    │
         │  │  │  │  │   Domain     │    │      │      │    │
         │  │  │  │  └──────────────┘    │      │      │    │
         │  │  │  └──────────────────────┘      │      │    │
         │  │  └────────────────────────────────┘      │    │
         │  └──────────────────────────────────────────┘    │
         └──────────────────────────────────────────────────┘
            ─────────────── dependency direction ───────────▶
                          (outside → inside)
```

## 4. ccprophet 계층별 매핑

### 4.1 Domain (`src/ccprophet/domain/`)

**엔티티**
- 기존: `Session`, `Event`, `ToolCall`, `ToolDef`, `FileAccess`, `Phase`, `Forecast`, `Subagent`, `BloatReport`
- 신규 (v0.4): `Recommendation`, `Snapshot`, `SubsetProfile`, `OutcomeLabel`, `BestConfig`, `PostmortemReport`, `CostBreakdown`, `PricingRate`, `SavingsEstimate`

**값 객체 (Value Objects, frozen dataclass)**
- 기존: `SessionId`, `EventId`, `TokenCount`, `BloatRatio`, `PhaseType`, `ToolSource`, `FilePathHash`, `RawHash`
- 신규: `Money(amount: Decimal, currency: str)`, `SnapshotId`, `RecommendationKind` (enum: `prune_mcp`·`prune_tool`·`run_clear`·`switch_subset`·`compact_focus`·`reproduce_config`), `OutcomeLabelValue` (enum: `success`·`fail`·`partial`·`unlabeled`), `TaskType`, `Confidence(0.0..1.0)`

**도메인 서비스 (순수 함수/클래스, 부수효과 없음)**
- 기존: `BloatCalculator.calculate(loaded, called) -> BloatReport`
- 기존: `PhaseDetector.detect(events) -> list[Phase]`
- 기존: `TokenUtilization.compute(loaded, referenced_ids) -> BloatRatio`
- **신규** `Recommender.recommend(session, bloat, phases, outcome_ctx) -> list[Recommendation]`
- **신규** `CostCalculator.session_cost(session, rates) -> CostBreakdown`
- **신규** `CostCalculator.realized_savings(before, after, rates) -> Money`
- **신규** `OutcomeClassifier.classify(session, events, rules) -> OutcomeLabel`
- **신규** `SessionClusterer.find_similar(target: Session, corpus: Sequence[Session]) -> list[Session]`
- **신규** `BestConfigExtractor.extract(cluster: Sequence[Session]) -> BestConfig`
- **신규** `PostmortemAnalyzer.analyze(fail: Session, success_cluster: Sequence[Session]) -> PostmortemReport`
- **신규** `SettingsPatchPlanner.plan(current: SettingsDoc, recs: Sequence[Recommendation]) -> SettingsDoc` (pure — IO는 Adapter)

**에러**
- `DomainError` base. 기존: `SessionNotFound`, `InvalidPhaseBoundary`, `NegativeTokenCount`.
- 신규: `InsufficientSamples`(n<3 등), `UnknownPricingModel`, `SnapshotConflict`(concurrent edit hash mismatch), `SnapshotMissing`, `ProfileNotFound`, `InvalidOutcomeRule`.

**Import 규칙**: stdlib + `dataclasses`·`typing`·`datetime`·`uuid`·`hashlib`·`enum`·`functools`·`decimal`만. `duckdb`/`rich`/`typer`/`tomllib`(=파일 IO) 등 제3자·stdlib-IO 라이브러리 금지. `json` 구조 계산은 허용하되 파일 접근은 Adapter 경유.

### 4.2 Use Cases (`src/ccprophet/use_cases/`)

1 파일 = 1 유스케이스 = 1 클래스 + 단일 `execute()`.

```python
# src/ccprophet/use_cases/analyze_bloat.py
from dataclasses import dataclass
from ccprophet.domain.entities import BloatReport
from ccprophet.domain.values import SessionId
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.ports.repositories import (
    SessionRepository, ToolDefRepository, ToolCallRepository,
)

@dataclass(frozen=True)
class AnalyzeBloatUseCase:
    sessions: SessionRepository
    tool_defs: ToolDefRepository
    tool_calls: ToolCallRepository

    def execute(self, session_id: SessionId) -> BloatReport:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        loaded = list(self.tool_defs.list_for_session(session_id))
        called = list(self.tool_calls.list_for_session(session_id))
        return BloatCalculator.calculate(loaded, called)
```

**목록** (Phase 1~3 계획)

*Phase 1 (Sellable MVP)*
- `IngestEventUseCase` ✓
- `AnalyzeBloatUseCase` ✓
- `DetectPhasesUseCase` ✓ (완료, v0.3 구현)
- **제품 A (Bloat + Auto Fix)**
  - `RecommendActionUseCase` — bloat/phase 기반 추천 생성
  - `PruneToolsUseCase` — `prune` 명령(dry-run 기본)
  - `ApplyPruningUseCase` — `prune --apply`, Auto-Fix Kernel 위임
  - `RestoreSnapshotUseCase` — `snapshot restore <id>`
  - `ListSnapshotsUseCase` — `snapshot list`
- **제품 B (Session Optimizer)**
  - `MarkOutcomeUseCase` — `mark <SID> --outcome ...`
  - `ClassifyOutcomeAutoUseCase` — 규칙 엔진 자동 라벨 (Phase 1 beta)
  - `EstimateBudgetUseCase` — `budget <task-type>`
  - `ReproduceSessionUseCase` — `reproduce <task-type> [--apply]`
  - `AnalyzePostmortemUseCase` — `postmortem <SID>`
  - `DiffSessionsUseCase` — `diff A B`
- **제품 C (Cost Dashboard)**
  - `ComputeSessionCostUseCase` — 단일 세션 환산
  - `ComputeMonthlyCostUseCase` — `cost --month`
  - `ComputeRealizedSavingsUseCase` — prune 전후 비교
- **공통**
  - `BackfillFromJsonlUseCase`

*Phase 2~3*
- `ForecastCompactUseCase`
- `GetPhaseBreakdownUseCase`
- `ReplaySessionUseCase`
- `ListRecommendationsUseCase` (history)

**Import 규칙**: `domain/`, `ports/`만. `tomllib`·`pathlib`·`os` 등 stdlib-IO도 금지 — Adapter를 통해서만 접근.

### 4.3 Ports (`src/ccprophet/ports/`)

#### 4.3.1 Driving Ports (Use Case Protocols)

Driving adapter가 Use Case 구체 클래스에 의존하지 않도록 Protocol export.

```python
# src/ccprophet/ports/use_cases.py
from typing import Protocol
from ccprophet.domain.entities import BloatReport
from ccprophet.domain.values import SessionId

class AnalyzeBloat(Protocol):
    def execute(self, session_id: SessionId) -> BloatReport: ...
```

#### 4.3.2 Driven Ports

```python
# src/ccprophet/ports/repositories.py
from typing import Protocol, Iterable
from datetime import datetime
from ccprophet.domain.entities import Event, Session, ToolCall, ToolDef
from ccprophet.domain.values import SessionId, RawHash

class EventRepository(Protocol):
    def append(self, event: Event) -> None: ...
    def dedup_hash_exists(self, raw_hash: RawHash) -> bool: ...
    def list_by_session(self, sid: SessionId) -> Iterable[Event]: ...

class SessionRepository(Protocol):
    def upsert(self, session: Session) -> None: ...
    def get(self, sid: SessionId) -> Session | None: ...
    def latest_active(self) -> Session | None: ...
    def list_recent(self, limit: int = 10) -> Sequence[Session]: ...
    def list_in_range(self, start: datetime, end: datetime) -> Sequence[Session]: ...
    def list_compacted_since(self, dt: datetime) -> Iterable[Session]: ...

class ToolDefRepository(Protocol):
    def bulk_add(self, sid: SessionId, defs: Iterable[ToolDef]) -> None: ...
    def list_for_session(self, sid: SessionId) -> Iterable[ToolDef]: ...

class ToolCallRepository(Protocol):
    def append(self, tc: ToolCall) -> None: ...
    def list_for_session(self, sid: SessionId) -> Iterable[ToolCall]: ...

class PhaseRepository(Protocol):
    def replace_for_session(self, sid: SessionId, phases: Sequence[Phase]) -> None: ...
    def list_for_session(self, sid: SessionId) -> Iterable[Phase]: ...

# ports/recommendations.py
class RecommendationRepository(Protocol):
    def save_all(self, recs: Sequence[Recommendation]) -> None: ...
    def list_for_session(self, sid: SessionId) -> Iterable[Recommendation]: ...
    def list_pending(self, limit: int = 50) -> Iterable[Recommendation]: ...
    def mark_applied(self, ids: Sequence[str], snapshot_id: SnapshotId) -> None: ...

# ports/snapshots.py
class SnapshotRepository(Protocol):
    """Metadata only. Actual file bytes handled by SnapshotStore."""
    def save(self, snap: Snapshot) -> None: ...
    def get(self, sid: SnapshotId) -> Snapshot | None: ...
    def list_recent(self, limit: int = 20) -> Sequence[Snapshot]: ...

class SnapshotStore(Protocol):
    """File-level capture/restore of config files."""
    def capture(self, files: Mapping[str, bytes], meta: SnapshotMeta) -> SnapshotId: ...
    def restore(self, sid: SnapshotId) -> Mapping[str, bytes]: ...

# ports/settings.py
class SettingsStore(Protocol):
    """Atomic read/write of .claude/settings.json and .mcp.json."""
    def read(self, path: Path) -> SettingsDoc: ...
    def hash_of(self, path: Path) -> str: ...
    def write_atomic(self, path: Path, doc: SettingsDoc, *,
                     expected_hash: str | None = None) -> None: ...

# ports/subset_profile.py
class SubsetProfileStore(Protocol):
    def save(self, profile: SubsetProfile) -> None: ...
    def load(self, name: str) -> SubsetProfile | None: ...
    def list_all(self) -> Sequence[SubsetProfile]: ...

# ports/pricing.py
class PricingProvider(Protocol):
    def rate_for(self, model: str) -> PricingRate: ...

# ports/outcomes.py
class OutcomeRepository(Protocol):
    def set_label(self, sid: SessionId, label: OutcomeLabel) -> None: ...
    def get_label(self, sid: SessionId) -> OutcomeLabel | None: ...
    def list_successful(self, task_type: TaskType) -> Sequence[Session]: ...

class OutcomeRulesProvider(Protocol):
    def rules(self) -> Sequence[OutcomeRule]: ...

# ports/clock.py
class Clock(Protocol):
    def now(self) -> datetime: ...

# ports/redactor.py
class Redactor(Protocol):
    def redact_path(self, path: str) -> str: ...
    def redact_command(self, cmd: str) -> str: ...
    def prompt_length_only(self, content: str) -> int: ...

# ports/forecast_model.py
class ForecastModel(Protocol):
    def fit(self, samples: Sequence[TokenSample]) -> None: ...
    def predict_compact_at(self, *, threshold: float) -> datetime | None: ...

# ports/publisher.py
class EventPublisher(Protocol):
    def publish(self, kind: str, payload: dict) -> None: ...

# ports/filewatch.py
class FileWatcher(Protocol):
    def start(self, on_change: Callable[[Path], None]) -> None: ...
    def stop(self) -> None: ...

# ports/logger.py
class Logger(Protocol):
    def info(self, msg: str, **fields: Any) -> None: ...
    def warn(self, msg: str, **fields: Any) -> None: ...
    def error(self, msg: str, exc: BaseException | None = None) -> None: ...
```

**Import 규칙**: `domain/`만. `typing.Protocol`·`dataclasses`·`pathlib.Path`(타입 힌트 전용)·`collections.abc`만. 실제 IO 코드 금지.

### 4.4 Adapters (`src/ccprophet/adapters/`)

#### 4.4.1 Driving Adapters (inbound)

외부 세계(사용자·프로세스)의 호출을 Use Case 호출로 변환.

| 어댑터 | 위치 | 변환 |
|---|---|---|
| CLI | `adapters/cli/` | argv → UseCase.execute() → Rich render |
| Web | `adapters/web/` | HTTP request → UseCase.execute() → JSON |
| MCP | `adapters/mcp/` | MCP tool call → UseCase.execute() → MCP response |
| Hook | `adapters/hook/` | stdin JSON → IngestEventUseCase.execute() |

#### 4.4.2 Driven Adapters (outbound)

Port를 구현해 실제 IO 수행.

| 어댑터 | 위치 | 구현 Port |
|---|---|---|
| `DuckDB*Repository` | `adapters/persistence/duckdb/` | Event/Session/ToolCall/ToolDef/Phase/Recommendation/Snapshot/Outcome |
| `InMemory*Repository` | `adapters/persistence/inmemory/` | 동일 Port (test fake) |
| `JsonFileSettingsStore` | `adapters/settings/jsonfile.py` | SettingsStore (atomic tmp+rename) |
| `FilesystemSnapshotStore` | `adapters/snapshot/filesystem.py` | SnapshotStore |
| `JsonFileSubsetProfileStore` | `adapters/subset_profile/jsonfile.py` | SubsetProfileStore |
| `BundledPricingProvider` | `adapters/pricing/bundled.py` | PricingProvider (패키지 내 `data/pricing.toml`) |
| `TomlOverridePricingProvider` | `adapters/pricing/tomloverride.py` | PricingProvider (user override wraps bundled) |
| `TomlOutcomeRulesProvider` | `adapters/outcome_rules/toml.py` | OutcomeRulesProvider |
| `SHA256Redactor` | `adapters/redaction/` | Redactor |
| `SystemClock`, `FrozenClock` | `adapters/clock/` | Clock |
| `LinearForecastModel` | `adapters/forecast/` | ForecastModel |
| `ArimaForecastModel` | `adapters/forecast/` | ForecastModel |
| `WatchdogTailer` | `adapters/filewatch/` | FileWatcher |
| `UnixSocketPublisher` | `adapters/publisher/` | EventPublisher |
| `RichLogger`, `JsonLogger` | `adapters/logger/` | Logger |

**Import 규칙**: `ports/`, `domain/`, 그리고 해당 어댑터가 의존하는 third-party. **다른 adapter 직접 import 금지** (교차 결합 방지) — 필요하면 Port를 통해, 아니면 harness에서 조립.

### 4.5 Harness (`src/ccprophet/harness/`)

엔트리포인트마다 하나의 파일. Adapter 생성·Use Case 주입·CLI/Server 시작만 담당.

```python
# src/ccprophet/harness/cli_main.py
from pathlib import Path
import duckdb, typer
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
from ccprophet.adapters.persistence.duckdb import (
    DuckDBSessionRepository, DuckDBToolDefRepository, DuckDBToolCallRepository,
)
from ccprophet.adapters.cli.bloat import make_bloat_command
# ...

def _db_path() -> Path:
    return Path.home() / ".claude-prophet" / "events.duckdb"

def build_analyze_bloat(conn) -> AnalyzeBloatUseCase:
    return AnalyzeBloatUseCase(
        sessions=DuckDBSessionRepository(conn),
        tool_defs=DuckDBToolDefRepository(conn),
        tool_calls=DuckDBToolCallRepository(conn),
    )

def main() -> None:
    conn = duckdb.connect(str(_db_path()), read_only=True)
    app = typer.Typer()
    app.command("bloat")(make_bloat_command(build_analyze_bloat(conn)))
    # ... 다른 커맨드
    app()
```

**목록**
- `harness/cli_main.py` — `ccprophet` 엔트리
- `harness/hook_main.py` — `ccprophet-hook` 엔트리 (stdlib만, 지연 import 최소화)
- `harness/web_main.py` — `ccprophet serve`
- `harness/mcp_main.py` — `ccprophet mcp`

**Import 규칙**: 모두 가능. 단 **로직 금지** — if/else·for로 비즈니스 분기를 하면 안 된다.

## 5. 의존성 방향 강제 (Enforcement)

### 5.1 정적 검증 — `import-linter`

```toml
# pyproject.toml
[tool.importlinter]
root_package = "ccprophet"

[[tool.importlinter.contracts]]
name = "Clean Architecture layers"
type = "layers"
layers = [
    "ccprophet.harness",
    "ccprophet.adapters",
    "ccprophet.use_cases",
    "ccprophet.ports",
    "ccprophet.domain",
]

[[tool.importlinter.contracts]]
name = "Domain is framework-free"
type = "forbidden"
source_modules = ["ccprophet.domain"]
forbidden_modules = [
    "duckdb", "fastapi", "starlette", "typer", "click", "rich",
    "watchdog", "mcp", "statsmodels", "httpx", "requests", "urllib3",
]

[[tool.importlinter.contracts]]
name = "Use cases and ports are framework-free"
type = "forbidden"
source_modules = ["ccprophet.use_cases", "ccprophet.ports"]
forbidden_modules = [
    "duckdb", "fastapi", "typer", "rich", "watchdog", "mcp", "statsmodels",
]

[[tool.importlinter.contracts]]
name = "Adapters do not import each other across families"
type = "independence"
modules = [
    "ccprophet.adapters.persistence",
    "ccprophet.adapters.cli",
    "ccprophet.adapters.web",
    "ccprophet.adapters.mcp",
    "ccprophet.adapters.hook",
    "ccprophet.adapters.forecast",
    "ccprophet.adapters.redaction",
    "ccprophet.adapters.filewatch",
    "ccprophet.adapters.publisher",
    "ccprophet.adapters.clock",
    "ccprophet.adapters.logger",
    "ccprophet.adapters.settings",
    "ccprophet.adapters.snapshot",
    "ccprophet.adapters.subset_profile",
    "ccprophet.adapters.pricing",
    "ccprophet.adapters.outcome_rules",
]
```

CI에서 `uv run lint-imports` 실행. 계약 위반 시 PR 거절.

### 5.2 런타임 규칙

Use Case 생성자는 Protocol 타입만 받는다. 구체 클래스·커넥션을 직접 받지 않는다.

```python
# ❌ 금지
class AnalyzeBloatUseCase:
    def __init__(self, conn: duckdb.DuckDBPyConnection): ...

# ✅ OK
class AnalyzeBloatUseCase:
    def __init__(self, sessions: SessionRepository, ...): ...
```

## 6. 디렉토리 레이아웃 (최종)

```
ccprophet/
├── pyproject.toml
├── uv.lock
├── CLAUDE.md
├── AGENTS.md
├── docs/
│   ├── PRD.md
│   ├── ARCHITECT.md
│   ├── DATAMODELING.md
│   ├── DESIGN.md
│   └── LAYERING.md          ← 본 문서
├── migrations/
│   └── V1__init.sql
├── web/                     # 빌드 스텝 없음
│   └── index.html
├── src/ccprophet/
│   ├── __init__.py
│   ├── data/
│   │   └── pricing.toml     # bundled pricing (packaged)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py
│   │   ├── values.py
│   │   ├── errors.py
│   │   └── services/
│   │       ├── bloat.py
│   │       ├── phase.py
│   │       ├── utilization.py
│   │       ├── recommender.py
│   │       ├── cost.py
│   │       ├── outcome.py
│   │       ├── cluster.py
│   │       ├── postmortem.py
│   │       └── settings_patch.py   # pure planner (IO는 adapter)
│   ├── use_cases/
│   │   ├── __init__.py
│   │   ├── ingest_event.py
│   │   ├── backfill_from_jsonl.py
│   │   ├── analyze_bloat.py
│   │   ├── detect_phases.py
│   │   ├── forecast_compact.py
│   │   ├── recommend_action.py
│   │   ├── prune_tools.py
│   │   ├── apply_pruning.py
│   │   ├── restore_snapshot.py
│   │   ├── list_snapshots.py
│   │   ├── mark_outcome.py
│   │   ├── classify_outcome_auto.py
│   │   ├── estimate_budget.py
│   │   ├── reproduce_session.py
│   │   ├── analyze_postmortem.py
│   │   ├── diff_sessions.py
│   │   ├── compute_session_cost.py
│   │   ├── compute_monthly_cost.py
│   │   └── compute_realized_savings.py
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── use_cases.py          # driving protocols
│   │   ├── repositories.py       # Event/Session/ToolCall/ToolDef/Phase
│   │   ├── recommendations.py    # RecommendationRepository
│   │   ├── snapshots.py          # SnapshotRepository + SnapshotStore
│   │   ├── settings.py           # SettingsStore
│   │   ├── subset_profile.py
│   │   ├── pricing.py
│   │   ├── outcomes.py           # OutcomeRepository + OutcomeRulesProvider
│   │   ├── clock.py
│   │   ├── redactor.py
│   │   ├── forecast_model.py
│   │   ├── publisher.py
│   │   ├── filewatch.py
│   │   └── logger.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── cli/             # driving
│   │   │   ├── __init__.py
│   │   │   ├── bloat.py
│   │   │   ├── live.py
│   │   │   ├── sessions.py
│   │   │   ├── recommend.py
│   │   │   ├── prune.py
│   │   │   ├── snapshot.py
│   │   │   ├── cost.py
│   │   │   ├── mark.py
│   │   │   ├── reproduce.py
│   │   │   ├── postmortem.py
│   │   │   └── install.py
│   │   ├── web/             # driving
│   │   │   ├── app.py
│   │   │   ├── routes/
│   │   │   └── ws.py
│   │   ├── mcp/             # driving (read-only)
│   │   │   └── server.py
│   │   ├── hook/            # driving
│   │   │   └── receiver.py
│   │   ├── persistence/
│   │   │   ├── duckdb/      # driven
│   │   │   │   ├── event_repository.py
│   │   │   │   ├── session_repository.py
│   │   │   │   ├── recommendation_repository.py
│   │   │   │   ├── snapshot_repository.py
│   │   │   │   ├── outcome_repository.py
│   │   │   │   └── migrations.py
│   │   │   └── inmemory/    # driven (test fakes)
│   │   │       └── repositories.py
│   │   ├── settings/
│   │   │   └── jsonfile.py
│   │   ├── snapshot/
│   │   │   └── filesystem.py
│   │   ├── subset_profile/
│   │   │   └── jsonfile.py
│   │   ├── pricing/
│   │   │   ├── bundled.py
│   │   │   └── tomloverride.py
│   │   ├── outcome_rules/
│   │   │   └── toml.py
│   │   ├── clock/
│   │   ├── redaction/
│   │   ├── forecast/
│   │   ├── filewatch/
│   │   ├── publisher/
│   │   └── logger/
│   └── harness/
│       ├── cli_main.py
│       ├── hook_main.py
│       ├── web_main.py
│       └── mcp_main.py
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── domain/
    │   │   ├── test_bloat_calculator.py
    │   │   ├── test_phase_detector.py
    │   │   └── test_values.py
    │   └── use_cases/
    │       ├── test_analyze_bloat.py
    │       └── test_detect_phases.py
    ├── contract/
    │   ├── test_event_repository_contract.py
    │   ├── test_session_repository_contract.py
    │   ├── test_clock_contract.py
    │   └── test_forecast_model_contract.py
    ├── integration/
    │   ├── adapters/
    │   │   ├── persistence/duckdb/
    │   │   ├── cli/
    │   │   ├── web/
    │   │   ├── mcp/
    │   │   └── hook/
    │   └── migrations/
    ├── e2e/
    │   └── test_install_and_analyze.py
    ├── perf/
    │   ├── test_hook_latency.py
    │   └── test_bloat_query.py
    ├── property/
    │   └── test_phase_detector_properties.py
    └── fixtures/
        ├── sample_session.jsonl
        ├── hook_payloads.json
        └── builders.py
```

## 7. 테스트 전략 (상세)

### 7.1 테스트 피라미드

```
                     ┌──────────────────┐
                     │   e2e   (≈3%)    │    uv run pytest tests/e2e
                     └──────────────────┘
                 ┌──────────────────────────┐
                 │  contract  (≈7%)         │    Port 계약 검증
                 └──────────────────────────┘
              ┌────────────────────────────────┐
              │  integration  (≈20%)           │    Adapter ↔ 실제 IO
              └────────────────────────────────┘
         ┌──────────────────────────────────────────┐
         │          unit  (≈70%)                    │    Domain + UseCase
         │  - domain: 순수 함수, 0 IO               │
         │  - use_cases: InMemory fake 주입         │
         └──────────────────────────────────────────┘

              + property-based (Hypothesis) — domain invariants
              + perf — 훅 p99, 쿼리 p95, DAG 렌더
```

### 7.2 계층별 테스트 정책

| 계층 | 종류 | 실제 IO | 도구 | 목표 실행 속도 | 커버리지 |
|---|---|---|---|---|---|
| `domain/` | Unit + Property | 없음 | pytest, Hypothesis | < 1ms/test | **≥ 95%** |
| `use_cases/` | Unit | 없음 (fake) | pytest | < 5ms/test | **≥ 90%** |
| `ports/` | 없음 (인터페이스) | — | — | — | N/A |
| `adapters/persistence/duckdb` | Integration + Contract | 실제 DuckDB | pytest + tmp_path | < 100ms/test | **≥ 85%** |
| `adapters/persistence/inmemory` | Contract | 없음 | pytest | < 5ms/test | 계약만 |
| `adapters/cli\|web\|mcp\|hook/` | Integration | stdin/HTTP/socket | CliRunner, httpx.AsyncClient, subprocess | < 200ms/test | **≥ 80%** |
| `adapters/forecast/` | Unit + stat | 없음 | pytest | < 50ms/test | ≥ 80% |
| `harness/` | Smoke | 전 스택 | subprocess | < 2s/test | ≥ 60% |

전체 목표: SM-8 (≥ 80%) 유지.

### 7.3 테스트 더블 정책

| 종류 | 정의 | 쓰는 곳 | 규칙 |
|---|---|---|---|
| **Fake** | Port를 메모리로 구현. 실제 로직 보유 | Use Case 유닛 테스트 | **기본값**. 같은 계약 테스트 통과해야 함 |
| **Stub** | 특정 질문에 고정값 반환 | 에러 경로 시뮬레이션 | 한 테스트 파일 내 로컬 사용 |
| **Mock** | 호출 기록·검증 | 부수효과 verify 필수일 때만 | `unittest.mock`. 남발 금지 — "왜 mock이 필요한가" 답해야 함 |
| **Spy** | 호출 카운트 기록 | Publisher 호출 검증 | InMemory 어댑터에 count 속성 |
| **Dummy** | 전달만 되고 안 쓰임 | 시그니처 채우기 | `object()` 또는 `None` 허용 |

**우선순위**: Fake ≫ Stub > Spy > Mock > Dummy. 결과(state) 기반 assertion이 호출(behavior) 기반보다 우선.

### 7.4 Fixture & Builder

```python
# tests/fixtures/builders.py
@dataclass
class SessionBuilder:
    id: SessionId = SessionId("7f8e9d2a")
    model: str = "claude-opus-4-6"
    started_at: datetime = datetime(2026, 4, 16, 9, 12, 34)
    ended_at: datetime | None = None
    total_input_tokens: int = 0
    compacted: bool = False

    def with_id(self, sid: str) -> "SessionBuilder":
        return replace(self, id=SessionId(sid))
    def compacted_at(self, dt: datetime) -> "SessionBuilder":
        return replace(self, compacted=True, ended_at=dt)
    def build(self) -> Session:
        return Session(**asdict(self))

class ToolCallBuilder: ...
class EventBuilder: ...

# tests/conftest.py
@pytest.fixture
def inmemory_repos():
    return InMemoryRepositorySet()

@pytest.fixture
def analyze_bloat(inmemory_repos):
    return AnalyzeBloatUseCase(
        sessions=inmemory_repos.sessions,
        tool_defs=inmemory_repos.tool_defs,
        tool_calls=inmemory_repos.tool_calls,
    )

@pytest.fixture
def tmp_duckdb(tmp_path):
    conn = duckdb.connect(str(tmp_path / "test.duckdb"))
    apply_migrations(conn)
    yield TmpDb(conn=conn, path=tmp_path / "test.duckdb")
    conn.close()
```

### 7.5 Domain 테스트 예시

```python
# tests/unit/domain/test_bloat_calculator.py
class TestBloatCalculator:
    def test_all_loaded_never_called_is_full_bloat(self):
        loaded = [ToolDef("mcp__github", TokenCount(1400), ToolSource("mcp:github"))]
        called: list[ToolCall] = []

        report = BloatCalculator.calculate(loaded, called)

        assert report.bloat_tokens == 1400
        assert report.bloat_ratio == BloatRatio(1.0)
        assert report.used_sources == set()

    def test_mixed_loaded_partial_called(self):
        loaded = [
            ToolDef("Read", TokenCount(100), ToolSource("system")),
            ToolDef("Bash", TokenCount(200), ToolSource("system")),
            ToolDef("mcp__jira_list", TokenCount(910), ToolSource("mcp:jira")),
        ]
        called = [ToolCallBuilder().for_tool("Read").build()]

        report = BloatCalculator.calculate(loaded, called)

        assert report.bloat_tokens == 200 + 910
        assert report.used_sources == {"system"}

    def test_empty_loaded_yields_zero_ratio(self):
        report = BloatCalculator.calculate([], [])
        assert report.bloat_ratio == BloatRatio(0.0)
        assert report.total_tokens == 0
```

### 7.6 Property-Based 테스트 예시

```python
# tests/property/test_phase_detector_properties.py
from hypothesis import given, strategies as st

event_strategy = st.builds(
    Event,
    event_type=st.sampled_from(["UserPromptSubmit", "PreToolUse", "PostToolUse"]),
    ts=st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2026, 12, 31)),
    # ...
)

@given(events=st.lists(event_strategy, min_size=1, max_size=200))
def test_every_event_is_in_exactly_one_phase(events):
    events_sorted = sorted(events, key=lambda e: e.ts)
    phases = PhaseDetector.detect(events_sorted)

    assigned = sum(len(p.event_ids) for p in phases)
    assert assigned == len(events_sorted)

@given(events=st.lists(event_strategy, min_size=1, max_size=200))
def test_phase_boundaries_are_non_overlapping_and_monotonic(events):
    events_sorted = sorted(events, key=lambda e: e.ts)
    phases = PhaseDetector.detect(events_sorted)
    for a, b in zip(phases, phases[1:]):
        assert a.end_ts <= b.start_ts
```

### 7.7 Use Case 테스트 예시

```python
# tests/unit/use_cases/test_analyze_bloat.py
class TestAnalyzeBloatUseCase:
    def test_returns_report_for_known_session(self, analyze_bloat, inmemory_repos):
        sid = SessionId("7f8e9d2a")
        inmemory_repos.sessions.upsert(SessionBuilder().with_id("7f8e9d2a").build())
        inmemory_repos.tool_defs.bulk_add(sid, [
            ToolDef("mcp__github", TokenCount(1400), ToolSource("mcp:github")),
            ToolDef("Read", TokenCount(1250), ToolSource("system")),
        ])
        inmemory_repos.tool_calls.append(
            ToolCallBuilder().in_session(sid).for_tool("Read").build()
        )

        report = analyze_bloat.execute(sid)

        assert report.bloat_tokens == 1400
        assert "system" in report.used_sources

    def test_raises_when_session_missing(self, analyze_bloat):
        with pytest.raises(SessionNotFound):
            analyze_bloat.execute(SessionId("does-not-exist"))

    def test_reads_are_read_only(self, analyze_bloat, inmemory_repos):
        """Use Case는 저장소에 write 하지 않는다."""
        sid = SessionId("7f8e9d2a")
        inmemory_repos.sessions.upsert(SessionBuilder().with_id("7f8e9d2a").build())

        snapshot_before = inmemory_repos.mutation_count()
        analyze_bloat.execute(sid)
        assert inmemory_repos.mutation_count() == snapshot_before
```

### 7.8 Contract 테스트 (Port 계약)

모든 Repository 구현이 통과해야 하는 공통 계약을 **추상 클래스**로 정의하고, Adapter별 테스트가 이를 상속한다.

```python
# tests/contract/test_event_repository_contract.py
class EventRepositoryContract(ABC):
    """EventRepository를 만족하는 모든 구현이 통과해야 하는 행동 계약."""

    @pytest.fixture
    @abstractmethod
    def repository(self) -> EventRepository: ...

    def test_append_then_list_returns_event(self, repository):
        event = EventBuilder().for_session("s1").build()
        repository.append(event)
        assert list(repository.list_by_session(SessionId("s1"))) == [event]

    def test_dedup_hash_prevents_double_insert(self, repository):
        event = EventBuilder().build()
        repository.append(event)
        assert repository.dedup_hash_exists(event.raw_hash) is True

    def test_list_returns_chronological_order(self, repository):
        e1 = EventBuilder().at("2026-04-16T09:00:00").build()
        e2 = EventBuilder().at("2026-04-16T09:00:01").build()
        repository.append(e2)
        repository.append(e1)
        events = list(repository.list_by_session(e1.session_id))
        assert events == [e1, e2]

    def test_unknown_session_returns_empty(self, repository):
        assert list(repository.list_by_session(SessionId("nope"))) == []

# tests/integration/adapters/persistence/duckdb/test_event_repo.py
class TestDuckDBEventRepository(EventRepositoryContract):
    @pytest.fixture
    def repository(self, tmp_duckdb):
        return DuckDBEventRepository(tmp_duckdb.conn)

# tests/unit/adapters/persistence/inmemory/test_event_repo.py
class TestInMemoryEventRepository(EventRepositoryContract):
    @pytest.fixture
    def repository(self):
        return InMemoryEventRepository()
```

`InMemoryEventRepository`도 동일 계약을 통과하므로 Use Case 유닛 테스트가 production 의미와 동치임을 보장.

### 7.9 Integration — Driven Adapter

```python
# tests/integration/adapters/persistence/duckdb/test_migrations.py
def test_v1_migration_creates_all_tables(tmp_duckdb):
    apply_migrations(tmp_duckdb.conn, up_to=1)
    got = {r[0] for r in tmp_duckdb.conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()}
    assert {
        "sessions", "events", "tool_calls", "tool_defs_loaded",
        "file_reads", "phases", "forecasts", "subagents",
        "prophet_self_metrics", "schema_migrations",
    } <= got

def test_migration_is_idempotent(tmp_duckdb):
    apply_migrations(tmp_duckdb.conn, up_to=1)
    apply_migrations(tmp_duckdb.conn, up_to=1)  # 두 번째 호출 실패 없어야 함
```

### 7.10 Integration — Driving Adapter

```python
# tests/integration/adapters/cli/test_bloat_command.py
from typer.testing import CliRunner

def test_bloat_prints_json_when_flag_passed(seeded_tmp_db, monkeypatch):
    monkeypatch.setenv("CCPROPHET_DB", str(seeded_tmp_db.path))
    runner = CliRunner()
    result = runner.invoke(cli_app, ["bloat", "--session", "7f8e9d2a", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "bloat_tokens" in payload
    assert isinstance(payload["sources"], list)

def test_bloat_exits_2_on_unknown_session(seeded_tmp_db, monkeypatch):
    monkeypatch.setenv("CCPROPHET_DB", str(seeded_tmp_db.path))
    runner = CliRunner()
    result = runner.invoke(cli_app, ["bloat", "--session", "nope"])
    assert result.exit_code == 2
    assert "not found" in result.stderr.lower()

# tests/integration/adapters/web/test_bloat_endpoint.py
@pytest.mark.asyncio
async def test_get_session_bloat_returns_200(client, seeded_web):
    r = await client.get("/api/sessions/7f8e9d2a/bloat")
    assert r.status_code == 200
    data = r.json()
    assert data["bloat_tokens"] >= 0

@pytest.mark.asyncio
async def test_get_unknown_session_returns_404(client, seeded_web):
    r = await client.get("/api/sessions/unknown/bloat")
    assert r.status_code == 404

# tests/integration/adapters/hook/test_hook_receiver.py
def test_hook_receiver_appends_event_under_50ms(tmp_duckdb, monkeypatch):
    monkeypatch.setenv("CCPROPHET_DB", str(tmp_duckdb.path))
    payload = json.dumps(load_fixture("posttooluse_sample.json")).encode()

    t0 = time.perf_counter()
    result = subprocess.run(
        ["ccprophet-hook", "--event", "PostToolUse"],
        input=payload, capture_output=True, timeout=1.0,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert result.returncode == 0
    assert elapsed_ms < 100  # single call, generous CI budget
    events = list(DuckDBEventRepository(duckdb.connect(str(tmp_duckdb.path))).list_by_session(
        SessionId(SAMPLE_SID)
    ))
    assert len(events) == 1

def test_hook_silent_fails_on_bad_payload(tmp_duckdb, monkeypatch):
    """AP-3 Silent Fail: 잘못된 payload여도 exit 0 + stderr 로그."""
    monkeypatch.setenv("CCPROPHET_DB", str(tmp_duckdb.path))
    result = subprocess.run(
        ["ccprophet-hook", "--event", "PostToolUse"],
        input=b"not json", capture_output=True, timeout=1.0,
    )
    assert result.returncode == 0  # Claude Code 세션을 막으면 안 됨

# tests/integration/adapters/mcp/test_mcp_server.py
def test_get_current_bloat_tool_responds_under_500ms(mcp_client_with_seeded_db):
    t0 = time.perf_counter()
    response = mcp_client_with_seeded_db.call_tool("get_current_bloat", {})
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 500
    assert "bloat_tokens" in response.content[0].text
```

### 7.11 E2E 스모크

```python
# tests/e2e/test_install_and_analyze.py
def test_happy_path_install_ingest_analyze(isolated_home):
    # 1. install
    r = subprocess.run(["uv", "run", "ccprophet", "install"], check=True, capture_output=True)
    assert (isolated_home / ".claude-prophet" / "events.duckdb").exists()

    # 2. 훅 시뮬레이션
    for payload in load_fixture_list("hook_payloads.json"):
        subprocess.run(
            ["uv", "run", "ccprophet-hook", "--event", payload["event"]],
            input=json.dumps(payload["body"]).encode(),
            check=True, capture_output=True, timeout=1.0,
        )

    # 3. 분석
    r = subprocess.run(
        ["uv", "run", "ccprophet", "bloat", "--json"],
        capture_output=True, check=True,
    )
    payload = json.loads(r.stdout)
    assert payload["bloat_tokens"] > 0
```

### 7.12 성능 테스트

```python
# tests/perf/test_hook_latency.py
@pytest.mark.perf
def test_hook_p99_under_50ms(tmp_duckdb, monkeypatch):
    """NFR-1: 훅 실행 p99 < 50ms."""
    monkeypatch.setenv("CCPROPHET_DB", str(tmp_duckdb.path))
    payloads = [json.dumps(p).encode() for p in load_fixture_list("hook_payloads.json")]

    durations_ms: list[float] = []
    for _ in range(10):  # warmup
        subprocess.run(["ccprophet-hook", "--event", "PostToolUse"],
                       input=payloads[0], capture_output=True)

    for p in payloads * 20:  # 최소 1000회
        t0 = time.perf_counter()
        subprocess.run(["ccprophet-hook", "--event", "PostToolUse"],
                       input=p, capture_output=True)
        durations_ms.append((time.perf_counter() - t0) * 1000)

    p99 = sorted(durations_ms)[int(len(durations_ms) * 0.99)]
    assert p99 < 50, f"p99={p99:.1f}ms exceeds 50ms budget (NFR-1)"

# tests/perf/test_bloat_query.py
@pytest.mark.perf
def test_30day_bloat_query_under_2s(large_seeded_db):
    """NFR: 30일 세션 bloat 집계 < 2s."""
    uc = build_analyze_bloat(large_seeded_db.conn)
    t0 = time.perf_counter()
    uc.execute_bulk(since=datetime.now() - timedelta(days=30))
    assert time.perf_counter() - t0 < 2.0
```

### 7.12.1 v0.4 신규 기능 테스트 가이드 (Auto-Fix / Cost / Outcome)

v0.4에서 추가된 파괴적·경제적 동작은 실수 비용이 크다. 다음 가이드를 반드시 따른다.

**Auto-Fix (SettingsStore, SnapshotStore, Apply*UseCase)**
- 모든 write 테스트는 **`tmp_path`** 위에서만 수행. 사용자의 `~/.claude/settings.json`에 닿지 않도록 Port 주입 경로 강제.
- `write_atomic` 계약 테스트: (1) 성공 시 내용 일치, (2) `expected_hash` 불일치면 `SnapshotConflict` raise, (3) 쓰기 도중 실패 시 원본 보존 (tmp 파일 남는지까지 확인).
- Snapshot round-trip 테스트: capture → 원본 파일 삭제 → restore → 바이트 동일. 복수 파일(settings.json + .mcp.json)도 커버.
- `ApplyPruningUseCase` 테스트: snapshot 기록이 먼저 일어남을 Spy로 검증 (call order). snapshot 실패 시 write 호출 금지.
- `RestoreSnapshotUseCase` 테스트: 부분 파일만 존재할 때도 manifest 기준으로 안전 복원.

**Cost (CostCalculator, PricingProvider)**
- `PricingProvider`는 Port 주입. 테스트는 **고정 요율의 `FakePricingProvider`** 사용 (bundled TOML 파싱 경로와 분리).
- `session_cost` 경계값: 0 tokens, cache_read/write 포함/미포함, 모델 매칭 실패(`UnknownPricingModel`).
- `realized_savings` 테스트: before/after 세션 쌍으로 예상값 계산. float 비교는 `pytest.approx(rel=1e-6)`.
- `pricing_rates`의 `effective_at` 이력 매칭: 세션 `started_at < effective_at`인 경우 제외되는지.

**Outcome (Classifier, Clusterer, BestConfigExtractor, Postmortem)**
- n<3 가드: `ReproduceSessionUseCase`는 성공 샘플이 2건 이하면 `InsufficientSamples` raise — 명시적 테스트 필수.
- `OutcomeClassifier`는 `OutcomeRulesProvider`를 Port로 주입. rule 엔진 자체 유닛 테스트와, provider로 주입한 use case 테스트를 분리.
- `BestConfigExtractor`는 결정적이어야 함 — 같은 입력 → 같은 출력. Hypothesis 속성으로 검증.
- `PostmortemAnalyzer`는 "Δ ≥ 2건"(SM-15) 조건을 case fixture로 고정.

**Recommender**
- Rule 엔진은 순수 함수. 각 `RecommendationKind`별 rule에 대해 (true condition / false condition / boundary) 3케이스.
- `confidence`는 항상 0.0~1.0 — Hypothesis로 invariant 검증.
- `rationale` 문자열은 템플릿 포맷 규약 유닛 테스트 (NFR-10 설명 가능성).

**Contract 테스트**: 모든 신규 Repository (`RecommendationRepository`·`SnapshotRepository`·`OutcomeRepository`·`SubsetProfileStore`·`PricingProvider`)는 `tests/contract/`에 공통 계약을 두고 InMemory·DuckDB 양쪽 adapter가 상속해 통과해야 한다.

### 7.13 Visual / DAG 회귀 (Playwright)

```python
# tests/integration/adapters/web/test_dag_visual.py
@pytest.mark.parametrize("node_count", [50, 500, 2000])
def test_dag_renders_within_budget(page, seeded_web_with_nodes, node_count):
    page.goto(f"http://localhost:8765/?session={seeded_web_with_nodes(node_count)}")
    page.wait_for_selector("[data-testid=dag-ready]", timeout=5000)
    # 스냅샷 회귀
    page.screenshot(path=f"snapshots/dag-{node_count}.png", full_page=True)
    # 성능 회귀
    metrics = page.evaluate("() => performance.getEntriesByName('dag:first-render')[0].duration")
    assert metrics < {50: 500, 500: 1000, 2000: 3000}[node_count]
```

## 8. 커버리지 목표 (계층별)

| 계층 | 라인 | 분기 |
|---|---|---|
| `domain/` | **≥ 95%** | ≥ 90% |
| `use_cases/` | **≥ 90%** | ≥ 85% |
| `ports/` | N/A | N/A |
| `adapters/persistence/` | **≥ 85%** | ≥ 75% |
| `adapters/cli\|web\|mcp\|hook/` | **≥ 80%** | ≥ 70% |
| `adapters/forecast/` | ≥ 80% | ≥ 70% |
| `harness/` | ≥ 60% | — |
| **전체 평균** | **≥ 80%** (SM-8) | ≥ 75% |

```bash
uv run pytest --cov=ccprophet --cov-branch \
  --cov-fail-under=80 \
  --cov-report=term-missing
```

추가로 `pyproject.toml`에 계층별 `--cov-fail-under` override를 `Makefile` 타깃으로 분리.

## 9. CI 파이프라인

```yaml
# .github/workflows/test.yml (요약)
jobs:
  lint-types:
    steps:
      - uv sync
      - uv run ruff check
      - uv run ruff format --check
      - uv run mypy src/ccprophet
      - uv run lint-imports              # Clean Arch 계약

  unit-and-property:
    steps:
      - uv sync
      - uv run pytest tests/unit tests/property --cov=ccprophet --cov-fail-under=90
      - uv run pytest tests/contract

  integration:
    needs: [unit-and-property]
    steps:
      - uv sync
      - uv run pytest tests/integration

  e2e:
    needs: [integration]
    steps:
      - uv sync
      - uv run pytest tests/e2e -k happy_path

  perf:
    needs: [integration]
    if: github.event_name == 'pull_request'
    steps:
      - uv sync
      - uv run pytest tests/perf -m perf --benchmark-only
```

**fail-fast 순서**: lint → unit → contract → integration → e2e → perf.
느린 계층은 빠른 계층이 통과한 뒤에만 실행.

## 10. 안티패턴 (금지)

| 안티패턴 | 이유 | 대체 |
|---|---|---|
| Use Case가 `duckdb.connect()` 직접 호출 | Domain이 framework에 오염 (LP-5 위반) | Repository Port 주입 |
| Domain entity가 ORM 모델 상속 | 영속 계층 결합 | dataclass + adapter 내 매핑 |
| Adapter가 다른 Adapter를 import | 교차 결합 | Port 경유, 또는 harness에서 조립 |
| Harness에 if/else 비즈니스 분기 | 로직이 composition root로 유출 | UseCase 내부로 이동 |
| Repository를 `Mock` 으로 스텁 | 어댑터 교체 시 재작성 | InMemory Fake + Contract 테스트 |
| SQL 안에 Phase 판정 로직 | 테스트·재사용 어려움 | Domain service로 추출, SQL은 조회만 |
| Forecast 훈련이 Analyzer에 삽입 | 교체 어려움 | ForecastModel Port + 어댑터 2개 |
| Test에서 `time.sleep` | flaky | FrozenClock 어댑터 사용 |
| Test가 production 로그 디렉토리에 씀 | 환경 오염 | `tmp_path` 픽스처 |
| Domain이 `datetime.now()` 직접 호출 | 시간 의존 테스트 flaky | Clock port 주입 |

## 11. 마이그레이션 (기존 코드 → 계층 구조)

ccprophet은 초기 단계이므로 처음부터 본 구조로 시작. 단, 구현 중 Adapter에 로직이 새는 징후 발견 시:

1. 해당 로직을 순수 함수로 추출해 `domain/services/`로 이동.
2. Adapter에는 호출만 남긴다.
3. 해당 도메인 서비스에 unit test 추가.
4. Contract test 통과 확인.

## 12. 오픈 질문

- **Q1**: Use Case I/O를 DTO로 명시할지, 엔티티·값 객체만 쓸지? (현재 제안: 단순 케이스는 값 객체, 3개 이상 파라미터 또는 응답 복합은 DTO)
- **Q2**: Port를 `typing.Protocol`(구조적)로 할지 `abc.ABC`(명목적)로 할지? (현재 제안: **Protocol** — 덕 타이핑, 선언 간결, InMemory fake 만들기 쉬움)
- **Q3**: Harness를 entrypoint별 파일로 분리할지, 단일 `compose.py`로 합칠지? (현재 제안: entrypoint별 분리, 각 ≤ 100 LOC)
- **Q4**: InMemory Adapter를 `src/`에 둘지 `tests/`에 둘지? (현재 제안: **`src/ccprophet/adapters/persistence/inmemory/`** — 다른 테스트·dev 툴에서도 재사용, 사이즈 작아 배포 영향 무시 가능)
- **Q5**: Contract 테스트를 각 Adapter 파일에 병치할지 `tests/contract/` 중앙화할지? (현재 제안: **중앙화** — 계약 자체가 1급 문서)
- **Q6**: Property-based 테스트 범위 — Domain service만 vs Use Case까지? (현재 제안: Domain service 우선, Use Case는 선택적)

---

**문서 종료**
