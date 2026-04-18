# ccprophet — Demo Screencast Script

**Target duration**: 2 min 30 sec (asciinema-friendly; GIF conversion via `asciicast2gif`).
**Tooling**: `asciinema rec demo.cast --cols=110 --rows=32`.
**Audience**: Claude Code power-user scrolling HN / Twitter / GitHub Explore.

Before you hit record:

```bash
# 1. Clean slate + deterministic seed
rm -f ~/.claude-prophet/demo.duckdb
export CCPROPHET_DB=~/.claude-prophet/demo.duckdb
uv run python scripts/seed_demo_db.py

# 2. Terminal window: dark theme, 110×32, monospace 14pt, no prompt clutter
export PS1='$ '
export PYTHONIOENCODING=utf-8
clear
```

The screencast has **5 scenes** mirroring the four killer features plus a hook/outro. Narration lines are the captions for a subtitle track or voiceover.

---

## Scene 0 · Hook (0:00–0:12)

```bash
$ ccprophet --help
```

*(Typer help renders; cursor hovers on the command list.)*

**Narration**: “You know Claude Code sometimes gets slower or dumber and you can't tell why. ccprophet is a local-first profiler that answers four questions at once.”

---

## Scene 1 · 🔧 Auto Fix — measure → prune → rollback (0:12–0:55)

```bash
$ ccprophet bloat --session sess-bloat --cost --json | jq '{bloat_ratio, bloat_tokens, bloat_cost_usd}'
```

Expected JSON slice:
```json
{
  "bloat_ratio": 0.891,
  "bloat_tokens": 12200,
  "bloat_cost_usd": 0.183
}
```

**Narration**: “Out of 13.7k tokens of loaded tools, 12.2k are unused. That's 89% bloat, $0.18 silently paid per session.”

```bash
$ ccprophet recommend --session sess-bloat --json --no-persist \
    | jq '.[0:3] | .[] | {kind, target, rationale}'
```

**Narration**: “Every recommendation comes with a rationale — AP-8 Explainable. We know which MCP to drop and why.”

```bash
# Apply — atomic write, snapshot-backed
$ ccprophet prune --target .claude/settings.json --apply --yes --json \
    | jq '{written, snapshot_id, applied_rec_ids}'
```

Expected:
```json
{
  "written": true,
  "snapshot_id": "47ed0…",
  "applied_rec_ids": ["…","…"]
}
```

**Narration**: “Applied via tmp + os.replace + SHA-256 hash guard. Zero risk of half-written settings. And if anything goes wrong…”

```bash
$ ccprophet snapshot restore 47ed0… --json | jq '.restored_paths'
```

**Narration**: “…one-step rollback. AP-7 Reversible Auto-Fix.”

---

## Scene 2 · 🎯 Session Optimizer — reproduce success (0:55–1:30)

```bash
$ ccprophet mark sess-succ --outcome success --task-type refactor-auth --json
$ ccprophet reproduce refactor-auth --json | jq '{task_type, cluster_size, common_tools}'
```

**Narration**: “Mark the sessions that worked. Next time you tackle the same task type, reproduce replays the winning tool subset — through the same atomic-write path as Auto Fix.”

```bash
$ ccprophet postmortem sess-bloat --md /tmp/postmortem.md && head -15 /tmp/postmortem.md
```

**Narration**: “And when a session fails, postmortem exports a one-page Markdown RCA you can drop straight into a retro.”

---

## Scene 3 · 💰 Cost Dashboard — tokens → dollars (1:30–1:55)

```bash
$ ccprophet cost --session sess-bloat --json \
    | jq '{total_cost, input_cost, output_cost, cache_creation_cost, cache_read_cost, rate_id}'
```

**Narration**: “Every cost number stamps the exact rate card used. Input, cache-creation, cache-read billed separately — no black-box pricing.”

```bash
$ ccprophet cost --month 2026-04 --json | jq '{session_count, total_cost, by_model}'
$ ccprophet savings --json | jq '{applied, pending}'
```

**Narration**: “Monthly totals per model. Savings dashboard tracks dollars saved by Auto Fix. AP-9 Dollar Transparency.”

---

## Scene 4 · 📊 Quality Watch — catch silent downgrades (1:55–2:18)

```bash
$ ccprophet quality --model claude-opus-4-7 --window 7d --baseline 30d --json \
    | jq '.[0] | {metric, baseline_mean, recent_mean, sigma, flagged, explanation}'
```

**Narration**: “Seven daily metrics — success rate, repeat-read rate, compact hit rate, output-length — z-scored against your own 30-day baseline. If the same model on the same options drifts by more than 2σ, it gets flagged with a one-line why.”

---

## Scene 5 · Outro (2:18–2:30)

```bash
$ ccprophet serve --port 8765 --open
```

*(Browser opens 127.0.0.1:8765 showing the Work DAG. Hold for 4 seconds, then Ctrl-C.)*

**Narration**: “Everything ships as a single DuckDB file, zero external network calls. `uv tool install ccprophet` and you're live in thirty seconds. Source on GitHub.”

---

## Rendering recipes

```bash
# Record
asciinema rec --cols=110 --rows=32 --overwrite demo.cast

# Convert to GIF (terminalizer or asciicast2gif)
asciinema2gif -w 1080 -t monokai demo.cast demo.gif

# Trim to social cuts (per-scene, for Twitter/Bluesky threads)
gifsicle --crop 0,0+1080x360 --use-colormap=web demo.gif > auto-fix.gif
```

## Alternative: pure GIF (no voiceover)

- **0:00** open with `ccprophet bloat --session sess-bloat --cost`
- **0:05** rich table renders; the 89.1% red chip is the visual hook
- **0:10** `prune --apply` → snapshot ID → `snapshot restore` → “settings.json identical to before”
- **0:20** cut to `cost --session` breakdown
- **0:25** cut to `quality` sparkline
- **0:30** outro: logo + “uv tool install ccprophet” + repo URL
