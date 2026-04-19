# Show HN draft — ccprophet

> Draft for the HN submission, Bluesky/Twitter thread, and the /r/programming crosspost. The post lead is deliberately problem-first, not feature-first; the product pitch rides shotgun.

---

## Title (≤80 chars)

**Show HN: ccprophet – fix Claude Code context waste and turn savings into dollars**

Alternate A: `Show HN: ccprophet – a local-first Claude Code profiler that auto-fixes bloat`
Alternate B: `Show HN: I got tired of guessing if Claude Code got dumber, so I built a profiler`

---

## Body

Hi HN,

I've been using Claude Code daily for the past few months and kept hitting the same three walls:

1. **Context waste is invisible.** I'd load 12 MCP servers "just in case" and never know which ones the model never called. My \$ bill said fine; my autocompact arrival time said otherwise.
2. **"Did Anthropic change something?"** That paranoid feeling after a good week suddenly becomes a bad one. Same model, same prompt style, worse answers — or so it feels. No data.
3. **Good sessions are forgettable.** Once I nailed a refactor with a tight tool subset and a specific `/clear` cadence, I couldn't remember what I did next time.

**ccprophet** is the tool I wanted. It's a local-first profiler for Claude Code that answers four questions through a single DuckDB file on your laptop:

- **"Don't tell me — fix it."** `ccprophet prune --apply` disables unused MCPs and tools with an atomic write + SHA-256 hash guard + snapshot, so a single `ccprophet snapshot restore <id>` is always one step behind.
- **"Not how much you used, but whether the result was better."** Mark successful sessions, and `ccprophet reproduce <task-type> --apply` replays the winning tool subset + env vars + /clear cadence.
- **"Not tokens — dollars."** Every cost output stamps the exact rate card row used (`pricing_rates.rate_id`), with input / cache_creation / cache_read billed separately. There is no black-box math.
- **"So Anthropic can't quietly downgrade you."** Seven daily metrics z-scored against your own 30-day baseline. Tool-call success rate drops 2σ on opus-4-7 at the same prompt length? You get a one-line "why".

### Architecture (for the curious)

- Python 3.10+, zero network calls by default, everything in one DuckDB file at `~/.claude-prophet/events.duckdb`.
- **Clean Architecture + Hexagonal**: `domain` (stdlib only) → `ports` (Protocols) → `use_cases` → `adapters` (DuckDB / FastAPI / Typer / MCP SDK / statsmodels) → `harness` (wiring only). Four `import-linter` contracts enforce the layer rules in CI.
- 533 tests across unit / contract / property / integration / perf pyramid, including an NFR-1 perf guard that asserts the hook's p99 latency stays under 50ms over 1000 samples.
- Data is collected via Claude Code's official hook points (PostToolUse, Stop, UserPromptSubmit, SubagentStop), JSONL backfill, and optional OTLP bridge. **No wrapping or spawning of Claude Code itself** — non-invasive by contract (AP-2).

### Try it (60 seconds)

```bash
uv tool install "ccprophet[web,mcp,forecast]"
ccprophet install               # hooks + statusLine + DB + schema migrations
ccprophet ingest                # backfills past Claude Code JSONL transcripts

# Then the four headline commands
ccprophet bloat --cost          # measure waste
ccprophet prune --apply         # fix it (snapshot + atomic)
ccprophet cost --month          # dollars, not tokens
ccprophet quality               # anti-downgrade watch
```

A local Web DAG viewer is one command away: `ccprophet serve` on `127.0.0.1:8765`.

### What's NOT in v0.6 (honest limitations)

- **`CCPROF_LOCALE` is deferred.** CLI is English-only for now.
- **Realized savings are computed from recommendations, not cost-delta.** Needs paired pre/post sessions that we don't yet capture. Estimated vs realized is explicit in the output.
- **Pricing overrides via `~/.claude-prophet/pricing.toml` are reserved.** Today, pricing is seeded via the V2 migration; edit `pricing_rates` via `ccprophet query run` if you need custom rates before Phase 2.
- **Typo suggestions** on the CLI (`ccprophet blat → bloat`) aren't wired yet.

### Why I'm posting it

- The AP-* / FR-* design rules are in `docs/` — tear them apart.
- The four killer features each have an E2E integration test — if you find a flow that should exist but doesn't, I want to know.
- PRs welcome, especially adapters for non-Claude-Code LLM CLIs (the hook receiver is pluggable).

License is MIT. Repo:

https://github.com/showjihyun/ccprophet

Happy to answer technical questions in comments.

---

## Twitter / Bluesky thread version

**Thread, 6 tweets:**

1. I built **ccprophet** — a local-first profiler for Claude Code that auto-fixes context waste and tells you the dollar cost. Zero network, single DuckDB file, MIT. 🧵

2. The pitch in four sentences:
   - Don't tell me — fix it.
   - Not how much you used, but whether the result was better.
   - Not tokens — dollars.
   - So Anthropic can't quietly downgrade you.

3. 🔧 **Auto Fix**: `ccprophet bloat → recommend → prune --apply → snapshot restore`. Snapshot + atomic write + SHA-256 hash guard. Concurrent edits raise `SnapshotConflict`. Rollback is one command.

4. 🎯 **Session Optimizer**: `mark` wins, `reproduce` replays them. Postmortem exports Markdown RCAs for retros.

5. 💰 **Cost Dashboard**: tokens → \$ with input / cache-creation / cache-read billed separately. Every number stamps the rate card row it used.

6. 📊 **Quality Watch**: 7 daily metrics · z-score vs your own 30-day baseline · 2σ threshold · 1-line "why" per flag. Built for the paranoid.

   `uv tool install ccprophet` → https://github.com/showjihyun/ccprophet

---

## /r/programming or /r/Python angle

Lead with the **Clean Architecture + Hexagonal** story:

> I spent weeks enforcing a layering contract with `import-linter` (4 separate rules), split the harness into a composition root that contains zero business logic, and made sure `domain/` uses stdlib only. Then I built a 533-test pyramid on top. Here's what that bought me when shipping a real tool.

Then the 4 killer features as "what the architecture enabled."

---

## Post-submission checklist

- [ ] Post on HN around 9am EST (Mon/Tue peak).
- [ ] Reply to the first 20 comments within 2h.
- [ ] Pin a comment linking to `CONTRIBUTING.md` and the issue templates.
- [ ] Cross-post to Bluesky within 30 min of HN.
- [ ] Watch the repo's star velocity; if it crosses 50 stars in an hour, add `ccprophet` to `awesome-claude-code` if a list exists.
