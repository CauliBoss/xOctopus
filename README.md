# xOctopus

xOctopus is a lightweight X Web content collector focused on post data. It avoids the official X API and uses a local browser session to capture public web responses that are available to the logged-in browser profile.

The current MVP includes a CLI, a local single-user Web dashboard, SQLite storage, optional media downloading, and lightweight scheduled collection.

## What It Does Not Do

xOctopus does not bypass private accounts, paywalls, blocks, captchas, login challenges, rate limits, or other access controls. It does not post, like, follow, repost, send messages, or otherwise automate account actions.

## Status

Early MVP. The CLI, Web dashboard, config loading, database schema, source management, JSONL export, Playwright response capture, raw response storage, and first-pass GraphQL timeline parsing are in place. The parser is intentionally conservative and should be expanded with saved real-world fixtures as X Web response shapes change.

## Install

For the CLI only:

```bash
pip install xoctopus
playwright install chromium
```

For the local Web dashboard:

```bash
pip install "xoctopus[web]"
playwright install chromium
```

## Install For Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev,web]"
playwright install chromium
```

## First Run

```bash
xoctopus init
xoctopus login
xoctopus run --once
xoctopus status
xoctopus --version
```

For detailed local testing steps, see [USAGE.md](USAGE.md).

For the lightweight local Web UI prototype notes, see [docs/web-prototype.md](docs/web-prototype.md).

## Core Commands

```bash
xoctopus init
xoctopus login
xoctopus source list
xoctopus source add user OpenAI
xoctopus source add search "(AI OR agent) -filter:replies"
xoctopus collect user OpenAI
xoctopus run --once
xoctopus run --watch
xoctopus status
xoctopus export --format jsonl --output exports/posts.jsonl
```

## Local Web Dashboard

The lightweight Web dashboard is available as a local single-user UI:

```bash
./xo web
```

Then open:

```text
http://127.0.0.1:8787
```

The Web UI reuses the same `config.toml`, SQLite database, browser profile, and
media library as the CLI. It currently includes:

```text
Dashboard
Posts
Media
Sources
Runs
Settings
```

Primary dashboard actions:

```text
Start Scheduler
Stop Scheduler
Run Once
Download Media
Reparse
Export JSONL
```

Use `Start Scheduler` on the Dashboard to run enabled sources repeatedly. Each
source uses its own `poll_interval_seconds` value from `config.toml`. Manual
actions remain available on the Dashboard; the global page header only keeps
navigation-level controls such as language switching.

After manual login is stable, headless collection can be enabled from
`Settings -> Browser collection` or directly in `config.toml`:

```toml
[browser]
headless = true
```

Headless mode removes the visible browser window during collection. Login and
security challenges should still be handled with a visible browser.

## Example: Scheduled Multi-Account Collection

After login succeeds, add multiple accounts to `config.toml`:

```toml
[[sources]]
name = "openai_timeline"
type = "user_timeline"
value = "OpenAI"
enabled = true
poll_interval_seconds = 1800

[[sources]]
name = "openai_devs_timeline"
type = "user_timeline"
value = "OpenAIDevs"
enabled = true
poll_interval_seconds = 1800

[[sources]]
name = "anthropic_timeline"
type = "user_timeline"
value = "AnthropicAI"
enabled = true
poll_interval_seconds = 3600
```

Run one collection pass and download pending media:

```bash
./xo run --once
./xo media download --limit 50
./xo posts --limit 10
./xo media list --limit 10
```

For a simple always-on local loop that collects text and then downloads media:

```bash
while true; do
  ./xo run --once
  ./xo media download --limit 50
  sleep 1800
done
```

For cron, set `browser.headless = true` in `config.toml` after login works, then add a job like this:

```cron
*/30 * * * * cd /home/light/Project/xOctopus && flock -n /tmp/xoctopus.lock ./xo run --once >> data/logs/cron.log 2>&1 && ./xo media download --limit 50 >> data/logs/cron.log 2>&1
```

Collected text is stored in SQLite and can be viewed with `./xo posts` or exported:

```bash
./xo export --format jsonl --output exports/posts.jsonl
```

Downloaded media is stored under:

```text
library/{username}/{post_id}/
```

## Boundaries

xOctopus does not bypass private account restrictions, blocks, captchas, paywalls, or access controls. If X presents a login challenge, captcha, rate limit, or account warning, the collector should pause and require manual review.

## Release Notes

Current package version: `0.2.0`.

Before publishing to GitHub, check:

```bash
./xo --version
uv run --extra dev --extra web python -m ruff check .
uv run --extra dev --extra web python -m pytest -q
uv build
uv run --extra dev twine check dist/*
```
