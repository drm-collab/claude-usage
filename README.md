# claude-usage

170-line Claude Code usage monitor. Shows your session limits, weekly usage, per-model breakdown, and time remaining — right in the status bar.

```
Max 5x  S:━━━━──── 52%  W:━━────── 22%  ⏱ 3h29m  Sonnet:12%
```

Zero dependencies. No themes. No animations. No auto-updater. Just the numbers.

## Install

```bash
python3 claude_usage.py --install
```

That's it. Restart Claude Code (or wait for the next status line refresh).

## What it shows

- **S:** Session usage (5-hour window) with color-coded bar
- **W:** Weekly usage (7-day rolling)
- **Per-model:** Opus/Sonnet breakdown when you have usage
- **Timer:** Countdown to session reset
- **Plan:** Auto-detected (Pro, Max 5x, Max 20x)
- **Extra credits:** Shows spend when enabled

Colors shift green → yellow → red as usage increases.

## How it works

Reads Claude Code's existing OAuth credentials (same ones you already use) and calls Anthropic's usage API. Tokens are domain-locked to `api.anthropic.com`, `console.anthropic.com`, and `platform.claude.com` — never sent anywhere else. Redirects to other domains are blocked.

## Why this exists

[claude-pulse](https://github.com/NoobyGains/claude-pulse) does the same thing in 3,287 lines with 10 themes, rainbow animations, gradient bar styles, auto-update from GitHub, and a GIF generator. This does it in 170 lines.

## License

MIT
