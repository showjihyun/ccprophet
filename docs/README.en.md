# ccprophet — English

**Context Efficiency Advisor for Claude Code** — a local-first auto-optimizer that measures *how well* you use your Claude Code context (not just how much), auto-fixes the waste, and converts the savings into dollars.

**Language** · [한국어](README.ko.md) · [English](README.en.md) · [中文](README.zh.md) · [🏠 root](../README.md)

---

## Why ccprophet?

Claude Code is powerful, but as sessions grow longer, your context is **silently wasted**. Unnecessary MCP servers, heavy system prompts, repeatedly-called tools, response quality that gradually drifts — nobody knows who is paying the cost, or how much.

ccprophet closes this gap. **Fully local** · **zero network** · **single DuckDB file**.

## Four-sentence promise

| # | Promise | What it means |
|---|---|---|
| 1 | **"Don't tell me — fix it"** | Disable MCPs, apply subset config, recommend `/clear` — all in one `apply`. |
| 2 | **"Not how much you used, but whether the result was better"** | Learn config + phase patterns from successful sessions and reproduce the best config. |
| 3 | **"Not token counts — dollars"** | Convert savings into monthly \$. |
| 4 | **"Spot regressions week-over-week"** | If quality metrics drop on the same model · same options, **auto-flag it**. Workload-sensitive: signal, not verdict. |

## The four killer features

### 1. 🔧 Auto Fix (Bloat → Prune → Snapshot → Rollback)
```bash
ccprophet bloat
ccprophet recommend              # evidence-backed (AP-8 Explainable)
ccprophet prune --apply          # atomic write with SHA-256 hash guard
ccprophet snapshot list
ccprophet snapshot restore <id>  # 1-step rollback (AP-7)
```
Write path: **snapshot → tmp + os.replace → hash guard → mark_applied**. Concurrent edits raise `SnapshotConflict`.

### 2. 🎯 Session Optimizer (reproduce your best config)
```bash
ccprophet mark <id> --outcome success --task-type refactor
ccprophet reproduce refactor --apply       # applies best config via same snapshot path
ccprophet postmortem <id> --md report.md   # failure RCA + Markdown export (FR-11.5)
ccprophet diff <a> <b>
ccprophet subagents
```

### 3. 💰 Cost Dashboard (tokens → dollars)
```bash
ccprophet cost --month                     # monthly \$ + per-model
ccprophet cost --session <id>              # per-session cost + cache hit
ccprophet savings --json                   # cumulative Auto Fix savings
```
Input · cache_creation · cache_read are **billed separately**. Every cost output stamps the `pricing_rates.rate_id` used — AP-9 Dollar Transparency.

### 4. 📊 Quality Watch (week-over-week regression flag)
```bash
ccprophet quality
ccprophet quality --export-parquet out.pq
```
Seven daily metrics aggregated per (model × task_type); z-score guard at 2σ by default. Output carries a 1-line "why" per flag. Metrics reflect workload mix as well as model behavior — treat as an early-warning signal, not a verdict.

## Install

```bash
uv tool install ccprophet
uv tool install "ccprophet[web,mcp,forecast]"

ccprophet install           # hooks · statusLine · DB init + schema migrations
ccprophet ingest            # backfill past Claude Code JSONL
# Short alias: `ccp` is installed alongside `ccprophet` — e.g. `ccp bloat`.
```
All data lives in one file at `~/.claude-prophet/events.duckdb`. **Zero external network calls.**

## Command catalog (29)

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

## Architecture

**Clean Architecture + Hexagonal**, enforced by 4 import-linter contracts:
```
harness/ ──▶ adapters/ ──▶ use_cases/ ──▶ ports/ ──▶ domain/
(wiring)     (DuckDB/FastAPI/..)   (Protocols only)   (stdlib only)
```
See [`LAYERING.md`](LAYERING.md) for layer rules and test strategy.

## Principles (AP-1 to AP-9)

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

## Development

```bash
uv sync --all-extras --dev
uv run pytest -q                     # 533 tests pass
uv run lint-imports                  # 4 contracts KEPT
uv run mypy src/ccprophet            # strict
uv run ruff check src/ tests/
uv run ccprophet serve               # http://127.0.0.1:8765
```
**Package manager is `uv` only — do not use `pip`** (AGENTS.md §1.4).

## Further docs

- [`PRD.md`](PRD.md) v0.6 — product requirements
- [`ARCHITECT.md`](ARCHITECT.md) v0.4 — architecture
- [`LAYERING.md`](LAYERING.md) v0.3 — layering & tests
- [`DATAMODELING.md`](DATAMODELING.md) v0.3 — DuckDB schema
- [`DESIGN.md`](DESIGN.md) v0.2 — CLI · Web design

## License

MIT
