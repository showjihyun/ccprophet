# Contributing to ccprophet

Thanks for your interest! ccprophet is an early-stage open-source project and
contributions are very welcome — bug reports, feature requests, docs, and PRs.

## Quick start

```bash
git clone https://github.com/showjihyun/ccprophet
cd ccprophet
uv sync --all-extras --dev          # installs dependencies into .venv
uv run pytest -q                    # should report "533 passed"
uv run lint-imports                 # 4 import-linter contracts
```

Package manager is **`uv` only** — no `pip`, no `poetry`. See [`AGENTS.md`](AGENTS.md) §1.4.

## Before opening a PR

1. **Run the full quality gate**:
   ```bash
   uv run pytest -q
   uv run lint-imports
   uv run ruff check src/ tests/
   uv run mypy src/ccprophet
   ```
2. **Update docs** if you change public behavior. Specifically:
   - New CLI command → update `docs/PRD.md` §6.3 command table, plus `docs/README.{ko,en,zh}.md`.
   - Schema change → add a new `migrations/V{N}__*.sql` AND update `docs/DATAMODELING.md` §8.3.
   - New Port or Use Case → update `docs/LAYERING.md` §4 + §6 tree.
3. **Add tests** following the pyramid: unit (70%) → contract (7%) → integration (20%) → e2e (3%). See `docs/LAYERING.md` §7.

## Architecture guardrails

ccprophet uses Clean Architecture + Hexagonal (Ports & Adapters), enforced by
four `import-linter` contracts. The key rules:

| Layer | Can import |
|---|---|
| `domain/` | stdlib only (no `duckdb`, `fastapi`, `rich`, etc.) |
| `use_cases/`, `ports/` | `domain/` + stdlib |
| `adapters/<family>/` | domain + ports + *own* third-party lib (e.g., `adapters/persistence/duckdb/` may import `duckdb`). **Never import another adapter family.** |
| `harness/` | anything — but only for composition / wiring |

CI will fail a PR that violates these. The contract file is `pyproject.toml [tool.importlinter]`.

## Reporting a bug

Include:
- `ccprophet --version` (e.g., `0.6.0`)
- OS + Python version (`python --version`)
- Output of `ccprophet doctor --json` if the DB is involved
- Exact command + stderr

## Proposing a feature

- If it's on the Phase 2 roadmap (`docs/PRD.md` §9), please link the section number.
- If it's new, please open an issue describing the *why* + expected CLI shape before writing code — saves a round trip.

## Code style

- Python 3.10+ with `from __future__ import annotations`.
- Formatter & linter: `ruff` (line-length 100).
- Type hints required. `mypy --strict` on `src/ccprophet`.
- Imports: stdlib → third-party → local. `ruff` enforces isort.

## License

By contributing you agree that your contributions are licensed under the MIT
License (same as the project — see [`LICENSE`](LICENSE)).
