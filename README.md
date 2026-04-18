# ccprophet

**Context Efficiency Advisor for Claude Code** — a local-first auto-optimizer that measures *how well* you use your Claude Code context (not just how much), auto-fixes the waste, and converts the savings into dollars.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-533%20passing-brightgreen)]()
[![Contracts](https://img.shields.io/badge/import--linter-4%2F4%20kept-6E56CF)]()
[![Architecture](https://img.shields.io/badge/arch-clean%20%2B%20hexagonal-6E56CF)]()
[![License](https://img.shields.io/badge/license-MIT-black)]()

## 🌐 Read in your language

| Language | 문서 / Doc / 文档 |
|---|---|
| 🇰🇷 한국어 | [`docs/README.ko.md`](docs/README.ko.md) |
| 🇬🇧 English | [`docs/README.en.md`](docs/README.en.md) |
| 🇨🇳 中文 | [`docs/README.zh.md`](docs/README.zh.md) |

---

## 30-second overview

```bash
# 1. Install (uv only — see AGENTS.md §1.4)
uv tool install "ccprophet[web,mcp,forecast]"

# 2. Wire into Claude Code + create the local DuckDB
ccprophet install
ccprophet doctor --migrate
ccprophet ingest                 # backfill past sessions

# 3. The four killer features
ccprophet bloat                  # 🔧 Auto Fix: measure waste
ccprophet prune --apply          #    snapshot → atomic write → 1-step rollback
ccprophet reproduce refactor --apply   # 🎯 Session Optimizer: apply best config
ccprophet cost --month           # 💰 Cost Dashboard: tokens → $
ccprophet quality                # 📊 Quality Watch: anti-downgrade
```

All data lives in `~/.claude-prophet/events.duckdb` — a single file, **zero external network calls**.

## Killer features at a glance

| | Feature | One-liner |
|---|---|---|
| 🔧 | **Auto Fix** | `bloat` → `recommend` → `prune --apply` → `snapshot restore` (AP-7 reversible) |
| 🎯 | **Session Optimizer** | `mark` successes, `reproduce` best config, `postmortem --md` failures (FR-11.5) |
| 💰 | **Cost Dashboard** | tokens → \$ with cache billing split; every rate stamped (AP-9) |
| 📊 | **Quality Watch** | 7 metrics · daily · z-score ≥ 2σ flag with 1-line "why" (AP-8) |

## Architecture (one picture)

```
harness/ ──▶ adapters/ ──▶ use_cases/ ──▶ ports/ ──▶ domain/
(wiring)     (DuckDB/FastAPI/..)   (Protocols only)   (stdlib only)
```
Enforced by 4 `import-linter` contracts in CI. See [`docs/LAYERING.md`](docs/LAYERING.md) v0.3.

## Quick dev loop

```bash
uv sync --all-extras --dev
uv run pytest -q                 # 533 tests
uv run lint-imports              # 4 contracts
uv run ccprophet serve           # http://127.0.0.1:8765
```

## Documentation

Language overviews:
- [`docs/README.ko.md`](docs/README.ko.md) · [`docs/README.en.md`](docs/README.en.md) · [`docs/README.zh.md`](docs/README.zh.md)

Spec (English inside, domain terms shared across languages):
- [`docs/PRD.md`](docs/PRD.md) v0.6 — product requirements · features F1–F12 · NFRs
- [`docs/ARCHITECT.md`](docs/ARCHITECT.md) v0.4 — architecture principles (AP-1..AP-9) · runtime · deployment
- [`docs/LAYERING.md`](docs/LAYERING.md) v0.3 — Clean + Hexagonal layering · test strategy
- [`docs/DATAMODELING.md`](docs/DATAMODELING.md) v0.3 — DuckDB schema · V1..V5 migrations
- [`docs/DESIGN.md`](docs/DESIGN.md) v0.2 — CLI · Web design system

Contributor guides:
- [`CLAUDE.md`](CLAUDE.md) — project instructions for Claude Code
- [`AGENTS.md`](AGENTS.md) — agent / tooling rules (uv-only, testing, CI)

## License

MIT
