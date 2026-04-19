# GitHub Social Preview + Landing-page assets

GitHub renders a **1280×640 PNG (≤ 1 MB)** at the top of every Twitter / Discord / Slack preview of the repo. This page documents the spec and checks in an SVG source you can export.

## Target assets

| Channel | Size | Source |
|---|---|---|
| GitHub Social preview | 1280×640 PNG | `docs/demo/social-preview.svg` (export via Inkscape or online SVG→PNG) |
| PyPI `long_description` hero | (rendered Markdown) | `README.md` first 40 lines |
| HN / Bluesky thread header | 1200×628 PNG (OG:image) | Same SVG, reframed crop |
| Blog hero | Wide 2400×1260 PNG | Same SVG, upscaled |

## Design brief

| Element | Content |
|---|---|
| Logo mark | `>_` prompt + a tiny DuckDB-duck silhouette or stacked bar ("bloat" → "fixed") |
| Wordmark | **ccprophet** (monospace, lowercase) |
| Tagline | `Context Efficiency Advisor for Claude Code` |
| Sub-tagline | `auto-fix bloat · tokens → $ · quality regression flag · local-first` |
| Backdrop | Near-black (`#0B0D10`) with a soft cyan glow behind the wordmark (`#6EE7F2`) — matches the rich-terminal theme users will see in the DAG viewer |
| Accents | Severity dots: green `#34D399`, yellow `#FBBF24`, red `#F87171` (same palette as DAG nodes) |

## SVG source (check in as `docs/demo/social-preview.svg`)

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 640" width="1280" height="640">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0B0D10"/>
      <stop offset="1" stop-color="#131821"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.28" cy="0.42" r="0.55">
      <stop offset="0" stop-color="#6EE7F2" stop-opacity="0.22"/>
      <stop offset="1" stop-color="#6EE7F2" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1280" height="640" fill="url(#bg)"/>
  <rect width="1280" height="640" fill="url(#glow)"/>

  <!-- prompt mark -->
  <g transform="translate(90,180)">
    <text x="0" y="0" fill="#6EE7F2" font-family="JetBrains Mono, monospace"
          font-size="72" font-weight="700">&gt;_</text>
  </g>

  <!-- wordmark -->
  <text x="90" y="340" fill="#F5F7FA" font-family="JetBrains Mono, monospace"
        font-size="118" font-weight="800" letter-spacing="-2">ccprophet</text>

  <!-- tagline -->
  <text x="90" y="400" fill="#A9B3BD" font-family="Inter, sans-serif"
        font-size="30" font-weight="500">Context Efficiency Advisor for Claude Code</text>

  <!-- sub-tagline: four promises -->
  <g font-family="Inter, sans-serif" font-size="22" font-weight="500">
    <text x="90"  y="470" fill="#34D399">🔧 auto-fix bloat</text>
    <text x="340" y="470" fill="#6EE7F2">🎯 reproduce wins</text>
    <text x="610" y="470" fill="#FBBF24">💰 tokens → $</text>
    <text x="860" y="470" fill="#F87171">📊 quality flag</text>
  </g>

  <!-- footer strip -->
  <text x="90" y="560" fill="#7C8691" font-family="JetBrains Mono, monospace"
        font-size="22">uv tool install ccprophet  ·  local-first  ·  zero network  ·  MIT</text>

  <!-- tiny repo handle bottom right -->
  <text x="1190" y="605" text-anchor="end" fill="#4B5560"
        font-family="JetBrains Mono, monospace" font-size="18">
    github.com/showjihyun/ccprophet
  </text>
</svg>
```

## Export recipe

```bash
# Inkscape (installed):
inkscape docs/demo/social-preview.svg \
  --export-type=png --export-width=1280 --export-filename=docs/demo/social-preview.png

# Or librsvg:
rsvg-convert -w 1280 -h 640 docs/demo/social-preview.svg > docs/demo/social-preview.png

# Or online: https://cloudconvert.com/svg-to-png (set width=1280, dpi=144)
```

Then upload via **GitHub → Settings → Social preview → Edit → Upload an image**.

## README hero section (PyPI-safe)

PyPI renders Markdown but **not images from relative paths**. Use inline SVG? No — PyPI strips `<svg>`. So keep the opening of `README.md` text-only but punchy. The current hero already does this:

- Line 1: bold tagline (one sentence, mentions "Claude Code" + "auto-optimizer" + "dollars")
- Line 2: four shields.io badges
- Line 3: language switcher table
- Line 4+: "30-second overview" code block

If you want a richer rendered landing page **on GitHub** (not PyPI), add an HTML hero block *inside a `<!-- -->` HTML comment* at the top of `README.md` — GitHub renders it, PyPI ignores it. Example:

```html
<!-- Hero — GitHub only, PyPI safely ignores -->
<p align="center">
  <img src="docs/demo/social-preview.png" alt="ccprophet" width="720">
</p>
```

GitHub honors that block; PyPI treats it as a comment.

## Open Graph tags for a marketing page (optional, future)

If we ever build a `ccprophet.dev` landing page:

```html
<meta property="og:title" content="ccprophet — Context Efficiency Advisor for Claude Code">
<meta property="og:description" content="Auto-fix Claude Code bloat. Reproduce wins. Tokens → dollars. Anti-downgrade. Local-first, MIT.">
<meta property="og:image" content="https://ccprophet.dev/social-preview.png">
<meta property="og:url" content="https://ccprophet.dev">
<meta name="twitter:card" content="summary_large_image">
```
