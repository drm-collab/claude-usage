#!/opt/homebrew/bin/python3
"""Lightweight Claude Code usage monitor — status line for the terminal.

Shows session usage, weekly usage, time remaining, model, and context.
Zero dependencies beyond stdlib. Reads Claude Code's existing OAuth credentials.

Install as status line:
    python3 scripts/claude_usage.py --install

Or run standalone:
    python3 scripts/claude_usage.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

VERSION = "1.0.0"

# Only send tokens to Anthropic-owned domains
_ALLOWED_DOMAINS = frozenset({"api.anthropic.com", "console.anthropic.com", "platform.claude.com"})

PLAN_NAMES = {
    "default_claude_ai": "Pro",
    "default_claude_max_5x": "Max 5x",
    "default_claude_max_20x": "Max 20x",
}

# ANSI
G = "\033[32m"   # green
Y = "\033[33m"   # yellow
R = "\033[31m"   # red
D = "\033[2m"    # dim
B = "\033[1m"    # bold
X = "\033[0m"    # reset


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).hostname not in _ALLOWED_DOMAINS:
            raise urllib.error.HTTPError(newurl, code, "redirect blocked", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _safe_request(url, token, headers=None):
    """HTTP request with token, domain-locked to Anthropic."""
    if urlparse(url).hostname not in _ALLOWED_DOMAINS:
        return None
    hdrs = {"User-Agent": f"claude-usage/{VERSION}"}
    if headers:
        hdrs.update(headers)
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=hdrs)
    opener = urllib.request.build_opener(_NoRedirect)
    return opener.open(req, timeout=10)


def get_credentials():
    """Read OAuth token from Claude Code's credential storage."""
    # 1. File
    creds_path = Path.home() / ".claude" / ".credentials.json"
    try:
        data = json.loads(creds_path.read_text())
        oauth = data.get("claudeAiOauth", {})
        token = oauth.get("accessToken")
        if token:
            tier = oauth.get("rateLimitTier", "")
            plan = PLAN_NAMES.get(tier, tier.replace("default_claude_", "").replace("_", " ").title())
            return token, plan
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # 2. macOS Keychain
    if sys.platform == "darwin":
        try:
            r = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout.strip())
                oauth = data.get("claudeAiOauth", {})
                token = oauth.get("accessToken")
                if token:
                    tier = oauth.get("rateLimitTier", "")
                    plan = PLAN_NAMES.get(tier, tier.replace("default_claude_", "").replace("_", " ").title())
                    return token, plan
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass

    # 3. Env var
    env_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if env_token:
        return env_token, ""

    return None, None


CACHE_FILE = Path.home() / ".claude" / ".usage_cache.json"
CACHE_TTL = 60  # seconds


def _read_cache():
    """Read cached usage data if fresh enough."""
    try:
        data = json.loads(CACHE_FILE.read_text())
        if time.time() - data.get("_ts", 0) < CACHE_TTL:
            return data
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def _write_cache(data):
    """Write usage data to cache."""
    try:
        data["_ts"] = time.time()
        CACHE_FILE.write_text(json.dumps(data))
    except OSError:
        pass


def fetch_usage(token):
    """Fetch usage data from Anthropic's OAuth usage API. Cached for 60s."""
    cached = _read_cache()
    if cached:
        return cached

    try:
        resp = _safe_request(
            "https://api.anthropic.com/api/oauth/usage",
            token,
            headers={"anthropic-beta": "oauth-2025-04-20", "Accept": "application/json"},
        )
        if resp:
            data = json.loads(resp.read(1_000_000))
            _write_cache(data)
            return data
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        # On rate limit or error, return stale cache if available
        try:
            return json.loads(CACHE_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    return None


def format_time_remaining(resets_at_str):
    """Format reset time as countdown."""
    if not resets_at_str:
        return "?"
    try:
        resets_at = datetime.fromisoformat(resets_at_str)
        secs = int((resets_at - datetime.now(timezone.utc)).total_seconds())
        if secs <= 0:
            return "now"
        h, m = secs // 3600, (secs % 3600) // 60
        return f"{h}h{m:02d}m" if h > 0 else f"{m}m"
    except (ValueError, TypeError):
        return "?"


def bar(pct, width=12):
    """Render a color-coded progress bar."""
    pct = max(0, min(100, pct))
    color = G if pct < 50 else Y if pct < 80 else R
    filled = round(pct / 100 * width)
    return f"{color}{'━' * filled}{D}{'─' * (width - filled)}{X}"


def render(usage):
    """Render the status line string."""
    if not usage:
        return f"{D}claude-usage: no data{X}"

    five = usage.get("five_hour", {})
    seven = usage.get("seven_day", {})

    session_pct = round(five.get("utilization") or 0)
    weekly_pct = round(seven.get("utilization") or 0)
    session_reset = format_time_remaining(five.get("resets_at"))

    weekly_reset = format_time_remaining(seven.get("resets_at"))

    parts = [
        f"S:{bar(session_pct, 8)} {session_pct}%  ⏱ {session_reset}",
        f"W:{bar(weekly_pct, 8)} {weekly_pct}%  ⏱ {weekly_reset}",
    ]

    # Per-model breakdown
    for key, label in [("seven_day_opus", "Opus"), ("seven_day_sonnet", "Sonnet")]:
        model = usage.get(key)
        if model and model.get("utilization"):
            util = round(model["utilization"])
            parts.append(f"{label}:{bar(util, 6)} {util}%")

    # Extra credits (API overflow)
    extra = usage.get("extra_usage", {})
    if extra and extra.get("is_enabled"):
        used = extra.get("used_credits", 0)
        limit = extra.get("monthly_limit", 0)
        remaining = limit - used
        parts.append(f"Credits: ${remaining:,.0f}/${limit:,.0f}")

    return "  ".join(parts)


def install():
    """Install as Claude Code status line."""
    script_path = str(Path(__file__).resolve())
    python_cmd = sys.executable
    settings_path = Path.home() / ".claude" / "settings.json"

    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            pass

    settings["statusLine"] = {
        "type": "command",
        "command": f'{python_cmd} "{script_path}"',
        "refresh": 150,
    }

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Installed status line: {python_cmd} \"{script_path}\"")
    print("Restart Claude Code to see it.")


def main():
    if "--install" in sys.argv:
        install()
        return
    if "--version" in sys.argv:
        print(f"claude-usage {VERSION}")
        return

    token, plan = get_credentials()
    if not token:
        print(f"{D}no credentials{X}")
        return

    usage = fetch_usage(token)
    line = render(usage)
    if plan:
        line = f"{B}{plan}{X}  {line}"
    print(line)


if __name__ == "__main__":
    main()
