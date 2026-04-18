---
name: Bug report
about: Something crashes, returns wrong data, or breaks a documented guarantee
title: "[bug] "
labels: bug
---

## Summary

One-line description of what went wrong.

## Reproduction

```bash
# Exact commands you ran, in order.
ccprophet install
ccprophet ...
```

## Expected vs actual

- Expected: …
- Actual: …

## Environment

- `ccprophet --version`: e.g. `0.6.0`
- OS + version: `macOS 14.4` / `Windows 11` / `Ubuntu 22.04`
- Python version (`python --version`): e.g. `3.12.1`
- Installed via: `uv tool install` / `uv sync` / editable / …
- Extras enabled: `web` / `mcp` / `forecast` (or none)

## Diagnostics

Paste the output of:

```bash
ccprophet doctor --json
```

If the hook is involved, also include the last few lines of:

```
~/.claude-prophet/logs/hook_errors.log
```

## Anything else

Screenshots, tracebacks, Claude Code version, network conditions, etc.
