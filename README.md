# xOctopus

xOctopus is a lightweight local collector for X Web content. It uses your own
logged-in browser session, stores captured responses in SQLite, preserves raw
JSON for later reparsing, and gives you a small Web dashboard for monitoring
sources, reading posts, and downloading media when needed.

It is built for local archiving and research workflows where posts are the main
asset and media files are optional attachments.

![xOctopus dashboard](assets/screenshots/dashboard.png)

## Highlights

- Local Web dashboard for day-to-day use
- CLI for scripts, cron, and automation
- SQLite storage with portable JSONL export
- Source management for users, searches, lists, posts, and media pages
- Browser-session collection through Playwright
- Raw response preservation so parser fixes can run later
- Optional media download workflow
- English and Chinese Web UI labels

## Web Dashboard

The Web UI is the easiest way to operate xOctopus. It reuses the same
`config.toml`, browser profile, SQLite database, and media library as the CLI.

Start it locally:

```bash
xoctopus web
```

Then open:

```text
http://127.0.0.1:8787
```

The dashboard shows collection state, source counts, raw event counts, recent
posts, recent runs, and pending media. From the first screen you can run one
collection pass, start or stop the scheduler, download media, reparse saved raw
responses, and export JSONL.

### Read And Filter Posts

![xOctopus posts](assets/screenshots/posts.png)

The Posts page is a local archive reader. Filter by username, keyword, media
presence, and result limit. Media stays collapsed by default so text review
stays fast; switch to archive-style browsing when you want to inspect attached
images and videos.

### Manage Sources

![xOctopus sources](assets/screenshots/sources.png)

Add monitored accounts, searches, media pages, list URLs, or individual post
URLs from the Sources page. Each source has its own enabled state and polling
interval, so high-signal feeds can run more often than slower archives.

## Install

For the Web dashboard:

```bash
pip install "xoctopus[web]"
playwright install chromium
```

For CLI-only use:

```bash
pip install xoctopus
playwright install chromium
```

On Linux systems where bundled Chromium is not suitable, install Chrome or
Chromium with your package manager and configure `browser.channel` or
`browser.executable_path` in `config.toml`.

## First Run

```bash
xoctopus init
xoctopus login
xoctopus web
```

`xoctopus login` opens a persistent browser profile. Log in manually, then
return to the terminal. Future collection runs reuse that local browser profile.

After login works, add sources in the Web UI or edit `config.toml` directly:

```toml
[[sources]]
name = "openai_timeline"
type = "user_timeline"
value = "OpenAI"
enabled = true
poll_interval_seconds = 1800
```

Run one pass:

```bash
xoctopus run --once
```

## Common CLI Commands

```bash
xoctopus init
xoctopus login
xoctopus web
xoctopus source list
xoctopus source add user OpenAI
xoctopus source add search "(AI OR agent) -filter:replies"
xoctopus collect user OpenAI
xoctopus run --once
xoctopus run --watch
xoctopus status
xoctopus posts --limit 20
xoctopus media list --pending
xoctopus media download --limit 50
xoctopus export --format jsonl --output exports/posts.jsonl
```

For a simple always-on local loop:

```bash
while true; do
  xoctopus run --once
  xoctopus media download --limit 50
  sleep 1800
done
```

For cron, set `browser.headless = true` after manual login works:

```cron
*/30 * * * * cd /path/to/xOctopus && flock -n /tmp/xoctopus.lock xoctopus run --once >> data/logs/cron.log 2>&1 && xoctopus media download --limit 50 >> data/logs/cron.log 2>&1
```

## Data Layout

```text
config.toml
data/xoctopus.sqlite3
data/browser-profile/
data/logs/
data/raw/
library/{username}/{post_id}/
exports/posts.jsonl
```

Text and metadata live in SQLite. Raw captured responses are retained for later
parser improvements. Downloaded media is stored under `library/`. Normalized
posts can be exported as JSONL.

## Boundaries

xOctopus does not bypass private accounts, paywalls, blocks, captchas, login
challenges, rate limits, or other access controls. It does not post, like,
follow, repost, send messages, or otherwise automate account actions.

If X presents a login challenge, captcha, rate limit, or account warning, pause
collection and resolve it manually in the browser.

## Status

Current package version: `0.2.3`.

xOctopus is an early MVP. The CLI, Web dashboard, SQLite storage, source
management, JSONL export, Playwright response capture, raw response storage, and
first-pass timeline/search parsing are in place. X Web response shapes change
often, so parser coverage should be expanded over time with saved raw fixtures.

For detailed local usage steps, see [USAGE.md](USAGE.md).
