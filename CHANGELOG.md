# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
format. This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] — 2026-04-18

First public release.

### Added — four killer features
- **Auto Fix** (F2 + F7): `bloat` → `recommend` → `prune --apply` → `snapshot restore`.
  Snapshot-backed atomic writes with SHA-256 hash-guard; concurrent-edit detection via
  `SnapshotConflict`.
- **Session Optimizer** (F8 + F11): `mark` / `budget` / `reproduce --apply` / `postmortem --md` / `diff` / `subagents`.
  Reproduces the best config from a cluster of labeled-success sessions through the
  same atomic-write pipeline as Auto Fix.
- **Cost Dashboard** (F10): `cost --session` / `cost --month` / `savings`. Input, cache_creation,
  cache_read billed separately; every output stamps the `pricing_rates.rate_id` used.
- **Quality Watch** (F12): `quality [--export-parquet]`. Seven daily metrics with z-score
  regression detection; one-line rationale per flag.

### Added — infrastructure
- 29 registered CLI commands (see `docs/README.en.md` command catalog).
- Local Web DAG viewer (`ccprophet serve` on `127.0.0.1:8765`) with DAG / Replay /
  Compare / Pattern Diff modes.
- Read-only MCP server (`ccprophet mcp`) mirroring 5 CLI use cases for self-introspection.
- Claude Code hook receiver (`ccprophet-hook`) with 2 MB payload cap and locale-neutral
  UTF-8 decoding.
- DuckDB schema V1–V5 with self-registering migrations.
- Pricing seeded via `V2__auto_fix_outcome_cost.sql` for `claude-opus-4-7` /
  `claude-sonnet-4-6` / `claude-haiku-4-5`.

### Architecture
- Clean Architecture + Hexagonal layering enforced by 4 `import-linter` contracts.
- 533 tests (unit 70% / contract 7% / integration 20% / property + perf guards).
- NFR-1 hook p99 < 50 ms, verified by `tests/perf/test_hook_latency.py`.

### Known limitations (Phase 2 roadmap)
- `CCPROF_LOCALE` env-var is accepted but user-facing strings are currently English-only.
- Realized cost savings are computed as the sum of `est_savings_usd` stamped at rec
  creation, not `cost(pre) - cost(post)` delta. Delta computation requires reference
  session pairs we don't yet capture.
- Pricing.toml override (user-supplied `~/.claude-prophet/pricing.toml`) is reserved
  but not wired — edit `pricing_rates` directly via `query run` until then.
- `CCPROPHET_OFFLINE=1` is accepted as a reserved no-op because ccprophet makes no
  network calls today. Honor the flag if you add any.

[0.6.0]: https://github.com/showjihyun/ccprophet/releases/tag/v0.6.0
