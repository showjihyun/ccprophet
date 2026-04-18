# ccprophet — Design System

**디자인 시스템 문서 (DESIGN)**

| 항목 | 내용 |
|---|---|
| 문서 버전 | 0.2 (Spec Sync) |
| 작성일 | 2026-04-18 |
| 상위 문서 | `PRD.md` v0.6, `ARCHITECT.md` v0.4 |
| 대상 독자 | 프론트엔드 컨트리뷰터, CLI 렌더링 담당, 디자이너 |
| 디자인 기조 | `shadcn/ui` — neutral palette, typography-first, minimal chrome |
| v0.2 갭 | v0.4 이후 추가된 Auto-Fix snapshot/rollback UX, Cost Dashboard, Quality Watch sparkline, Pattern Diff, Subagent timeline 의 디자인 토큰·컴포넌트는 본 문서에 아직 반영되지 않았다. 개별 UX 상세는 `ARCHITECT.md` §4.4/§4.7/§4.8 을 canonical source 로 참조. 디자인 시스템 통합은 Phase 2. |

---

## 1. 문서 목적

본 문서는 `ccprophet`이 노출하는 세 가지 UI 접점 — **CLI (Rich terminal)**, **Web Viewer (DAG)**, **Statusline** — 의 시각 언어를 정의한다. 이름은 "프로파일러"이지만 사용자가 매일 보는 결과물이므로, 조용하고 신뢰감 있는 도구처럼 느껴져야 한다. `shadcn/ui`의 디자인 철학을 가이드로 삼는다: **장식 없이 정보 밀도만 높게, 타이포그래피로 위계를, neutral palette로 일관성을.**

## 2. 디자인 원칙 (Design Principles)

**DP-1. Typography over Chrome**
UI 요소가 주장하지 않는다. 숫자·레이블·구분선이 스스로 위계를 만든다. Border와 background는 미세한 tint로만 존재.

**DP-2. Monochrome Base, Single Accent**
기본 palette는 zinc/neutral 계열 grayscale. 강조색은 한 번에 하나만 (status 표시용 semantic color는 예외).

**DP-3. Dark-First, Light-Parity**
개발자 터미널·IDE 맥락. 다크 모드를 1차 디자인 기준으로 잡고 라이트 모드는 token 반전만으로 도출.

**DP-4. Density with Breathing Room**
정보 밀도는 높이되 4px grid로 호흡한다. 한 화면에 많이 보여주되, 각 요소는 padding으로 분리.

**DP-5. Motion as Feedback, Not Decoration**
애니메이션은 "상태가 변했다"를 알리는 용도. 150ms 이하, ease-out. 장식성 motion 금지.

**DP-6. Terminal-Web Parity**
CLI와 Web이 같은 데이터를 보여줄 때는 같은 레이블·순서·색을 쓴다. 사용자가 두 접점을 오가도 인지 비용이 없다.

## 3. 디자인 토큰 (Design Tokens)

shadcn/ui의 CSS 변수 네이밍을 그대로 따른다. `config.toml`의 `[theme]` 섹션에서 override 가능.

### 3.1 Color Tokens — Dark Mode (기본)

| Token | HSL | Hex | 용도 |
|---|---|---|---|
| `--background` | `240 10% 4%` | `#0a0a0b` | 페이지/터미널 배경 |
| `--foreground` | `0 0% 98%` | `#fafafa` | 기본 텍스트 |
| `--card` | `240 6% 10%` | `#18181a` | 카드/패널 배경 |
| `--card-foreground` | `0 0% 98%` | `#fafafa` | 카드 내 텍스트 |
| `--popover` | `240 6% 10%` | `#18181a` | 툴팁/팝오버 |
| `--primary` | `0 0% 98%` | `#fafafa` | 주요 CTA (다크에선 흰색) |
| `--primary-foreground` | `240 6% 10%` | `#18181a` | primary 위 텍스트 |
| `--secondary` | `240 4% 16%` | `#27272a` | 보조 버튼/칩 |
| `--secondary-foreground` | `0 0% 98%` | `#fafafa` | secondary 텍스트 |
| `--muted` | `240 4% 16%` | `#27272a` | 비활성 배경 |
| `--muted-foreground` | `240 5% 65%` | `#a1a1aa` | 보조 텍스트 (메타데이터) |
| `--accent` | `240 4% 16%` | `#27272a` | hover/selected |
| `--accent-foreground` | `0 0% 98%` | `#fafafa` | accent 위 텍스트 |
| `--border` | `240 4% 16%` | `#27272a` | 구분선 |
| `--input` | `240 4% 16%` | `#27272a` | 입력 필드 border |
| `--ring` | `240 5% 65%` | `#a1a1aa` | focus ring |

### 3.2 Color Tokens — Light Mode

| Token | HSL | Hex | 용도 |
|---|---|---|---|
| `--background` | `0 0% 100%` | `#ffffff` | 페이지 배경 |
| `--foreground` | `240 10% 4%` | `#0a0a0b` | 기본 텍스트 |
| `--card` | `0 0% 100%` | `#ffffff` | 카드 배경 |
| `--muted` | `240 5% 96%` | `#f4f4f5` | 비활성 배경 |
| `--muted-foreground` | `240 4% 46%` | `#71717a` | 보조 텍스트 |
| `--border` | `240 6% 90%` | `#e4e4e7` | 구분선 |
| `--primary` | `240 6% 10%` | `#18181a` | 주요 CTA |

### 3.3 Semantic Color Tokens

상태 표시 전용. 다크/라이트 공통.

| Token | Hex (Dark) | Hex (Light) | 의미 |
|---|---|---|---|
| `--success` | `#22c55e` | `#16a34a` | 정상 호출, USED |
| `--warning` | `#eab308` | `#ca8a04` | 임계치 근접, 주의 |
| `--destructive` | `#ef4444` | `#dc2626` | BLOAT, 에러, compact 임박 |
| `--info` | `#3b82f6` | `#2563eb` | 예측·추천 액션 |

**규칙**: semantic color는 **텍스트나 아이콘의 전경색**으로만 사용. 큰 면적 background로 쓰지 않는다 (DP-2).

### 3.4 Typography Tokens

| Token | Value | 용도 |
|---|---|---|
| `--font-sans` | `ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif` | 기본 |
| `--font-mono` | `ui-monospace, "JetBrains Mono", "SF Mono", Consolas, monospace` | 숫자·ID·SQL |
| `--text-xs` | 12px / 1rem | 배지, 메타 |
| `--text-sm` | 13px / 1.25rem | 본문 보조, 테이블 |
| `--text-base` | 14px / 1.5rem | 본문 |
| `--text-lg` | 16px / 1.75rem | 섹션 헤더 |
| `--text-xl` | 20px / 1.75rem | 페이지 타이틀 |
| `--text-2xl` | 24px / 2rem | 대시보드 KPI |
| `--text-3xl` | 30px / 2.25rem | 마커 수치 (토큰·%) |

**Weights**: 400 (regular), 500 (medium), 600 (semibold). 700 이상 사용 금지 (DP-1).

### 3.5 Spacing Scale (4px base)

```
0.5 = 2px    1 = 4px     2 = 8px     3 = 12px
4   = 16px   5 = 20px    6 = 24px    8 = 32px
10  = 40px   12 = 48px   16 = 64px   20 = 80px
```

카드 padding: `p-6` (24px), 섹션 간격: `gap-8` (32px), 인라인 간격: `gap-2` (8px).

### 3.6 Border Radius

| Token | Value | 용도 |
|---|---|---|
| `--radius-sm` | 4px | 배지, 작은 인풋 |
| `--radius` | 8px | 버튼, 입력 필드 (기본) |
| `--radius-lg` | 12px | 카드, 패널 |
| `--radius-xl` | 16px | 모달, 대시보드 컨테이너 |

shadcn의 `--radius` 변수처럼 단일 루트 값(8px)을 기준으로 ±4px 파생.

### 3.7 Shadows

거의 쓰지 않는다 (DP-1). 필요 시에만.

| Token | Value |
|---|---|
| `--shadow-sm` | `0 1px 2px 0 rgb(0 0 0 / 0.05)` |
| `--shadow` | `0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)` |
| `--shadow-md` | `0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)` |

다크 모드에서는 shadow를 border 강조로 대체 (shadcn 관례).

## 4. 컴포넌트 라이브러리 (Components)

Web Viewer에서 쓰이는 기본 컴포넌트. vanilla JS로 구현하되 shadcn/ui 컴포넌트와 시각적으로 동일하게 만든다.

### 4.1 Button

```
┌────────────────┐
│  Run Analysis  │  ← Primary (default)
└────────────────┘

┌────────────────┐
│  Export JSON   │  ← Secondary (outlined)
└────────────────┘

  Skip this →       ← Ghost (text only, muted)
```

**Variants**: `default`, `secondary`, `ghost`, `destructive`, `link`.
**Sizes**: `sm` (h-8), `default` (h-9), `lg` (h-10).
**States**: default, hover (opacity 0.9), focus (ring), disabled (opacity 0.5).

### 4.2 Card

DAG 사이드 패널, bloat 리포트 각 항목, 세션 목록 카드 등에 재사용.

```
┌──────────────────────────────────────┐
│  Session 7f8e9d2a                    │  ← CardHeader
│  Started 09:12 · Model opus-4-6      │  ← CardDescription (muted)
├──────────────────────────────────────┤
│                                      │  ← CardContent
│  142,850 input · 23,410 output       │     (text-2xl mono for numbers)
│  Bloat: 12.4% (17,820 tokens)        │
│                                      │
├──────────────────────────────────────┤
│  [  View Details  ]                  │  ← CardFooter
└──────────────────────────────────────┘
```

- `border: 1px solid var(--border)`, `radius: var(--radius-lg)`, `bg: var(--card)`.
- 내부 구분선은 `border-t border-[--border]`.

### 4.3 Badge

Tool source 표시, status, phase type 표시.

| Variant | 시각 | 용도 |
|---|---|---|
| `default` | 흰 배경 / 검은 글씨 (dark는 반전) | 기본 |
| `secondary` | muted 배경 | 메타 레이블 (`mcp:github`) |
| `outline` | 투명 / border만 | 중립 태그 (phase name) |
| `destructive` | 붉은 틴트 / 붉은 글씨 | `BLOAT`, `FAILED` |
| `success` | 초록 틴트 / 초록 글씨 | `USED`, `OK` |

크기: `text-xs px-2 py-0.5 rounded-[--radius-sm]`.

### 4.4 Table

Bloat 리포트, Phase breakdown의 핵심.

```
┌─────────────────┬──────────┬─────────┬────────┐
│ Source          │  Tokens  │ Bloat % │ Status │  ← thead (muted-foreground, text-xs, uppercase)
├─────────────────┼──────────┼─────────┼────────┤
│ mcp:github      │   1,400  │ 100.0%  │ [BLOAT]│
│ mcp:jira        │     910  │ 100.0%  │ [BLOAT]│
│ system          │   2,130  │   0.0%  │ [USED] │
└─────────────────┴──────────┴─────────┴────────┘
```

- thead: `text-xs uppercase tracking-wide text-muted-foreground`.
- tbody 셀: `text-sm`, 숫자는 `font-mono tabular-nums text-right`.
- row hover: `bg-accent`.
- 구분선은 `border-b border-[--border]`만 (vertical border 없음).
- zebra stripe 사용 안 함 (DP-1).

### 4.5 Input / Select / Command

shadcn의 `<Command>` 팔레트 스타일. Web Viewer에서 session 검색·필터에 사용.

```
┌──────────────────────────────────────────┐
│ 🔍  Search sessions...                   │
├──────────────────────────────────────────┤
│  Recent                                  │  ← group label (muted, text-xs)
│  ▸ 7f8e9d2a — kahis-zavis  2h ago        │  ← row (py-2 px-3)
│  ▸ 3c1a4b2f — ccprophet    yesterday     │
│  ──────────────────────                  │
│  Actions                                 │
│  ▸ Export as Parquet         ⌘E          │
└──────────────────────────────────────────┘
```

### 4.6 Tabs

Web Viewer 상단 (DAG / Bloat / Phase / Forecast).

```
━━━━━━━━━━   ────────   ────────   ────────
   DAG         Bloat      Phase     Forecast
```

Active tab: `border-b-2 border-[--foreground]` + `text-foreground`.
Inactive: `text-muted-foreground`.
no background, no pill.

### 4.7 Dialog / Sheet

Session 상세, plugin 설정. `backdrop: rgba(0,0,0,0.8)` + `bg-[--card]` container.

### 4.8 Toast

훅 설치 완료, 아카이브 저장 같은 시스템 알림. 우측 하단, 4s auto-dismiss.

```
┌──────────────────────────────────────┐
│ ✓  Hooks installed                   │
│    4 event listeners registered      │
└──────────────────────────────────────┘
```

### 4.9 Tooltip

DAG 노드 hover 시. `text-xs`, `bg-[--popover]`, `border`, `p-3`.

### 4.10 Progress / Bar

Context 사용률 표시용 horizontal bar.

```
Context usage
██████████████░░░░░░░░░░░░░░░░  47% / 200k
```

- Background: `bg-[--muted]` (h-2 rounded-full).
- Fill: 임계치에 따라 색 전환 — <70% `--foreground`, 70~90% `--warning`, >90% `--destructive`.

## 5. DAG 시각화 스타일 (Graph View)

F4 Work DAG 웹뷰의 시각 언어.

### 5.1 Node Style

```
       ╭──────────────╮
       │              │
       │   Session    │   ← circle/rounded-rect
       │   9d2a       │
       │              │
       ╰──────────────╯
```

| 노드 타입 | 도형 | 크기 기준 | 기본 색상 |
|---|---|---|---|
| Session | 굵은 원 | 고정 r=32 | `--foreground` stroke, transparent fill |
| Subagent | 얇은 원 | log(tokens) | `--muted-foreground` stroke |
| Phase | 둥근 사각형 | 호흡용 고정 크기 | dashed border |
| Tool call | 점 | log(input_tokens) | bloat면 `--destructive`, used면 `--foreground` |
| File read | 마름모 | log(tokens) | `referenced=true` → solid, `false` → outline only |
| MCP server | 육각형 | log(sum tokens) | source별 고유 grayscale tint |

**색으로 bloat를 말하지 않는다** — 노드 fill이 **비어있음(outline only)** 이 bloat의 시그널. 색은 semantic 상태(error/warning) 전용.

### 5.2 Edge Style

- 호출 edge: 실선 `stroke-[--muted-foreground]`, 두께 = `log(call_count)`.
- 참조 edge (file→output): 점선.
- 자식 관계 (session→subagent): 굵은 실선.
- Hover 시 연결 edge는 `--foreground`로 강조, 나머지는 opacity 0.3.

### 5.3 Layout

- Phase 1: D3 force-directed, 중력 약하게 (-30), link distance 60.
- 500 노드 초과 시 Cytoscape.js `cose-bilkent` layout으로 자동 전환.
- 뷰 좌측 상단에 mini-map 제공 (100x100 fixed).

### 5.4 Side Panel

노드 클릭 시 우측 400px 고정 sheet 슬라이드 인.

```
┌─────────────────────────────────┐
│  mcp:github                  ✕  │
│  ─────────────────────────────  │
│                                 │
│  Tokens loaded     1,400        │  ← text-2xl mono
│  Times called          0        │
│  Bloat ratio      100.0%        │
│                                 │
│  ─────────────────────────────  │
│  Raw definition                 │  ← Accordion
│  ▸ show JSONL excerpt           │
│                                 │
│  Recommended action             │
│  [  Disable this server  ]      │
└─────────────────────────────────┘
```

## 6. CLI / Rich Terminal Styling

Web의 토큰을 터미널에 매핑. `rich`의 `Theme` 객체로 일괄 관리.

### 6.1 ANSI → Token Mapping

| Token | Rich style 이름 | Terminal fallback |
|---|---|---|
| `--foreground` | `default` | 터미널 기본색 |
| `--muted-foreground` | `dim` | `ansi bright_black` |
| `--border` | `dim` | `ansi bright_black` |
| `--success` | `bold green` | `ansi green` |
| `--warning` | `bold yellow` | `ansi yellow` |
| `--destructive` | `bold red` | `ansi red` |
| `--info` | `bold cyan` | `ansi cyan` |

```python
# ccprophet/ui/theme.py
THEME = Theme({
    "foreground": "default",
    "muted": "dim",
    "border": "dim white",
    "success": "bold green",
    "warning": "bold yellow",
    "destructive": "bold red",
    "info": "bold cyan",
    "kbd": "reverse",
    "number": "bold",
})
```

### 6.2 표준 Rich 렌더

**Bloat 리포트 — Table**
```
                       Bloat Report
                       ━━━━━━━━━━━━
  ┌─────────────┬────────┬────────┬─────────┐
  │ Source      │ Tokens │ Bloat% │ Status  │
  ├─────────────┼────────┼────────┼─────────┤
  │ mcp:github  │  1,400 │ 100.0% │ ✕ BLOAT │
  │ mcp:jira    │    910 │ 100.0% │ ✕ BLOAT │
  │ system      │  2,130 │   0.0% │ ✓ USED  │
  └─────────────┴────────┴────────┴─────────┘

  Total bloat: 2,960 tokens (1.5% of session)
  Run `ccprophet recommend` for action items.
```

- `box=box.ROUNDED`, `header_style="muted"`, `border_style="border"`.
- 숫자는 `justify="right"`, `style="number"`.

**Live 대시보드 — Layout**
- 상단: KPI 한 줄 (`Panel(title="Session 7f8e9d2a")`).
- 중단: Progress bar × 3 (context, bloat, forecast).
- 하단: Sparkline (최근 60s input token rate).
- refresh: 1Hz (`Live(refresh_per_second=1)`).

### 6.3 Statusline (한 줄 요약)

Claude Code의 `statusLine` 통합.

```
 ⚡ 47k/200k · bloat 12% · ~8m to compact 
```

- 길이: 터미널 폭 - 20 (clip).
- 구분자: ` · ` (공백 포함 미들닷, U+00B7).
- 이모지 1개만 사용 (⚡=live). 많을수록 가독성 하락.
- 컨텍스트 >85%면 전체 배경 `--destructive`.

## 7. 아이콘 (Iconography)

- **Web Viewer**: [Lucide](https://lucide.dev) icon set. stroke-width 1.5, size 16.
- **CLI**: Nerd Font 가정하지 않음 (compat 우선). 이모지도 최소화 — `✓ ✕ → · ⚡` 5종만.
- 아이콘은 항상 텍스트 레이블과 **함께** (단독 아이콘 버튼 금지 — 접근성).

| 용도 | Lucide | Terminal |
|---|---|---|
| Session | `activity` | ⚡ |
| Bloat | `trash-2` | ✕ |
| Used | `check` | ✓ |
| File read | `file-text` | · |
| MCP server | `plug` | · |
| Forecast | `trending-up` | → |
| Warning | `alert-triangle` | ! |

## 8. 모션 & 인터랙션 (Motion)

**Timing tokens**

| Token | Duration | Easing | 용도 |
|---|---|---|---|
| `--motion-fast` | 100ms | `ease-out` | hover 색 전환 |
| `--motion` | 150ms | `ease-out` | tab 전환, 패널 토글 |
| `--motion-slow` | 250ms | `cubic-bezier(0.16, 1, 0.3, 1)` | sheet 슬라이드 |

**규칙**
- 250ms 초과 금지 (DP-5).
- DAG simulation tick은 별도 예외 — physics-based라 duration 개념 없음.
- `prefers-reduced-motion` 존중: motion 없이 instant 전환.

## 9. 접근성 (Accessibility)

- **대비**: 모든 텍스트/배경 조합은 WCAG AA (4.5:1) 이상. `--muted-foreground`가 최저값이며 라이트 모드에서 `#71717a`/`#ffffff` = 4.61:1 OK.
- **Focus 가시성**: `--ring` 2px offset 1px, 모든 인터랙티브 요소 필수.
- **키보드**: 모든 상호작용은 키보드만으로 가능. `Tab`/`Shift+Tab` 순서는 시각적 순서와 일치.
- **ARIA**: Table에 `<caption>`, Dialog에 `aria-labelledby`, Badge에 `aria-label` (status 의미를 색에만 의존 금지).
- **Terminal 색맹**: Bloat 표시를 색 단독으로 하지 않는다. 항상 `✕` 글리프를 동반.

## 10. 레이아웃 (Layout)

### 10.1 Web Viewer 전체 구조

```
┌─────────────────────────────────────────────────────────────┐
│  ccprophet · localhost:8765                      [  ⚙ ]     │  ← TopBar (h-14, border-b)
├──────────────┬──────────────────────────────────────────────┤
│              │  DAG  │  Bloat  │  Phase  │  Forecast        │  ← Tabs (h-10)
│   Sidebar    ├──────────────────────────────────────────────┤
│   ━━━━━━     │                                              │
│   Sessions   │                                              │
│   ▸ 9d2a     │                Main Content                  │
│   ▸ 3c1a     │                (DAG / Table)                 │
│   ▸ …        │                                              │
│              │                                              │
│   (w-64)     │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

- TopBar: `h-14`, `border-b`, `bg-[--background]/80 backdrop-blur`.
- Sidebar: `w-64`, `border-r`, session 리스트 (virtualized).
- Main: `flex-1`, padding `p-6`.
- 1280px 이하에선 sidebar collapse.

### 10.2 Breakpoints

| Name | Width |
|---|---|
| `sm` | 640px |
| `md` | 768px |
| `lg` | 1024px |
| `xl` | 1280px |
| `2xl` | 1536px |

주 타겟은 `xl` 이상 (개발자 데스크탑).

## 11. Empty / Loading / Error 상태

### 11.1 Empty State

```
┌─────────────────────────────────────┐
│                                     │
│              ⌘                      │
│                                     │
│      No sessions yet                │   ← text-lg font-medium
│      Run `ccprophet install` to     │   ← text-sm text-muted
│      register hooks                 │
│                                     │
│      [  View install guide  ]       │   ← secondary button
│                                     │
└─────────────────────────────────────┘
```

center aligned, aspect-ratio 유지, 단일 CTA.

### 11.2 Loading Skeleton

테이블/카드 shape을 유지하되 `bg-[--muted]`로 replace, `animate-pulse` (1.5s).
Spinner는 사용하지 않는다 (DP-5).

### 11.3 Error State

```
┌─────────────────────────────────────┐
│  ⚠  Failed to load session          │  ← text-destructive
│                                     │
│  DuckDB file at                     │
│  ~/.claude-prophet/events.duckdb    │
│  is locked by another process.      │
│                                     │
│  [  Retry  ]   [  Open logs  ]      │
└─────────────────────────────────────┘
```

- 제목에만 `--destructive` 색상, 본문은 `--foreground`.
- 복구 액션 2개까지. "그냥 다시 시도" 외에 구체적 경로 제시.

## 12. 검증·테스트 (Visual Regression)

- Storybook + Chromatic으로 각 컴포넌트 state snapshot.
- 다크/라이트 두 테마 모두 캡처.
- CLI는 `rich.console.Console(record=True)` + SVG export로 고정 출력 스냅샷 비교.
- Playwright visual test — DAG 100/500/2000 노드 3종 샘플.

## 13. 샘플 구현 (Reference Snippets)

### 13.1 Tailwind Config (shadcn/ui 호환)

```js
// tailwind.config.js
export default {
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
    },
  },
}
```

### 13.2 globals.css

```css
@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 240 10% 4%;
    --card: 0 0% 100%;
    --muted: 240 5% 96%;
    --muted-foreground: 240 4% 46%;
    --border: 240 6% 90%;
    --primary: 240 6% 10%;
    --primary-foreground: 0 0% 98%;
    --destructive: 0 72% 51%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 240 10% 4%;
    --foreground: 0 0% 98%;
    --card: 240 6% 10%;
    --muted: 240 4% 16%;
    --muted-foreground: 240 5% 65%;
    --border: 240 4% 16%;
    --primary: 0 0% 98%;
    --primary-foreground: 240 6% 10%;
    --destructive: 0 63% 50%;
  }
}
```

### 13.3 Rich Theme (Python)

```python
# ccprophet/ui/theme.py
from rich.theme import Theme
from rich.style import Style

CCPROPHET_THEME = Theme({
    "foreground": Style(),
    "muted": Style(dim=True),
    "border": Style(dim=True, color="white"),
    "success": Style(color="green", bold=True),
    "warning": Style(color="yellow", bold=True),
    "destructive": Style(color="red", bold=True),
    "info": Style(color="cyan", bold=True),
    "number": Style(bold=True),
    "kbd": Style(reverse=True),
    "badge.bloat": Style(color="red", reverse=True),
    "badge.used": Style(color="green", reverse=True),
})
```

## 14. 오픈 질문 (Open Questions)

- **Q1**: accent 1색을 지정할 것인가 (예: violet-500)? 현재 제안: **지정 안 함** — semantic 4색만으로 충분. shadcn 기본도 무채색.
- **Q2**: 라이트 모드 출시 범위 — v0.1은 다크 only, v0.2에서 light 추가?
- **Q3**: 한글 본문 폰트 — system default에 맡길지 Pretendard를 self-host할지. (현재 제안: system)
- **Q4**: DAG에서 bloat를 outline으로만 표현 vs 추가적인 해치(hatch) 패턴? 색맹 친화 차원에서 hatch가 안전하나 복잡도 증가.
- **Q5**: CLI에서 Unicode 글리프(`✓ ✕ ━ ┌`)를 쓰는 정도 — Windows cmd.exe 호환 모드를 위한 ASCII fallback flag 필요?

---

**문서 종료**
