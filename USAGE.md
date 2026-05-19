# xOctopus Usage Guide

This document is a practical local usage guide for xOctopus.

xOctopus collects X Web JSON responses through a local browser profile, stores raw responses in SQLite, parses post data, and exports normalized posts as JSONL. It does not use the official X API and does not bypass login, captcha, private accounts, rate limits, or other access controls.

## 1. Prepare Environment

Use Python 3.10 or newer.

With `uv`:

```bash
uv sync --extra web
uv run playwright install chromium
```

On Ubuntu 26.04, Playwright may report that bundled Chromium is unsupported. In
that case, install a system Chrome/Chromium browser and configure xOctopus to use
it instead of running `uv run playwright install chromium`.

Or with `venv` and `pip`:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[web]"
playwright install chromium
```

Check the CLI:

```bash
uv run xoctopus --help
```

If you use an activated virtual environment, run `xoctopus --help` instead.

This repository also includes a short helper command:

```bash
./xo --help
```

All later `uv run xoctopus ...` examples can be shortened to `./xo ...`.

## 2. Initialize Project Data

Create `config.toml`, runtime directories, and the SQLite database:

```bash
uv run xoctopus init
```

Short form:

```bash
./xo init
```

Expected local files and directories:

```text
config.toml
data/xoctopus.sqlite3
data/browser-profile/
data/logs/
data/raw/
library/
```

`config.toml` is copied from `config.example.toml` the first time. If it already exists, `init` keeps the existing file.

## 3. Log In To X

Open a persistent Chromium profile:

```bash
uv run xoctopus login
```

Short form:

```bash
./xo login
```

A browser window opens at X. Log in manually, then return to the terminal and press Enter to close the browser. The session is saved under:

```text
data/browser-profile/
```

If X shows captcha, account warning, or another manual challenge, resolve it in the browser. xOctopus does not bypass those checks.

`login` uses a normal system Chrome/Chromium process when one is configured in
`config.toml`. This avoids login providers rejecting a Playwright-controlled
browser. After login, collection reuses the same browser profile.

If a third-party login button still says the browser is not secure, use X's
username/email and password login flow in the opened browser.

## 4. Configure Sources

View current sources:

```bash
uv run xoctopus source list
```

Short form:

```bash
./xo source list
```

Generate a config snippet for a user timeline:

```bash
uv run xoctopus source add user OpenAI
```

Generate a config snippet for a search:

```bash
uv run xoctopus source add search "(AI OR agent) -filter:replies"
```

Copy the printed `[[sources]]` block into `config.toml`. Supported source types:

```text
user      -> user_timeline
media     -> user_media
search    -> search
list      -> list URL
post      -> post URL
```

Example:

```toml
[[sources]]
name = "openai_timeline"
type = "user_timeline"
value = "OpenAI"
enabled = true
poll_interval_seconds = 1800
```

## 5. Run A One-Off Collection

Collect a single source without editing `config.toml`:

```bash
uv run xoctopus collect user OpenAI
```

Short form:

```bash
./xo collect user OpenAI
```

Collect a configured source pass:

```bash
uv run xoctopus run --once
```

Short form:

```bash
./xo run --once
```

Default `xoctopus run` behavior is the same as `xoctopus run --once`.

Run continuously:

```bash
uv run xoctopus run --watch
```

Stop watch mode with Ctrl+C.

## 6. Scheduled Multi-Account Collection

Add one `[[sources]]` block per account in `config.toml`:

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

Test the full text-plus-media workflow once:

```bash
./xo run --once
./xo media download --limit 50
./xo status
./xo posts --limit 10
./xo media list --limit 10
```

Use this local loop when you want a simple foreground scheduler:

```bash
while true; do
  ./xo run --once
  ./xo media download --limit 50
  sleep 1800
done
```

After manual login works, cron jobs should use headless collection:

```toml
[browser]
headless = true
```

Then install a cron job with `crontab -e`:

```cron
*/30 * * * * cd /home/light/Project/xOctopus && flock -n /tmp/xoctopus.lock ./xo run --once >> data/logs/cron.log 2>&1 && ./xo media download --limit 50 >> data/logs/cron.log 2>&1
```

This example runs every 30 minutes. `flock` prevents overlapping runs if a
previous collection is still active.

Use smaller media batches if downloads are slow:

```bash
./xo media download --type photo --limit 20
./xo media download --type video --limit 5
```

## 7. Check Status

Show table counts and source status:

```bash
uv run xoctopus status
```

Short form:

```bash
./xo status
```

Important tables:

```text
sources       configured collection rules
raw_events    captured X Web JSON responses
authors       parsed X users
posts         parsed X posts
media_assets  reserved for optional media downloading
fetch_runs    collection run history
```

## 8. Run The Local Web Dashboard

Start the lightweight local Web UI:

```bash
./xo web
```

Open:

```text
http://127.0.0.1:8787
```

The Web dashboard uses the same `config.toml`, `data/xoctopus.sqlite3`, and
`library/` as the terminal commands.

Available views:

```text
Dashboard
Posts
Media
Sources
Runs
Settings
```

Dashboard actions:

```text
Start Scheduler
Stop Scheduler
Run Once
Download Media
Reparse
Export JSONL
```

`Start Scheduler` runs enabled sources repeatedly inside the Web process. Each
source uses its configured `poll_interval_seconds`; disabled sources are skipped.
Use `Stop Scheduler` before shutting down the Web process if you want a clean
manual stop.

Manual actions are intentionally kept on the Dashboard instead of every page:

```text
Run Once          collect all enabled sources immediately
Download Media    download pending media assets
Reparse           rebuild posts from saved raw responses
Export JSONL      export normalized posts
```

The top-right header stays reserved for global UI controls such as language
switching.

## 9. Export Posts

View recently collected posts in readable cards:

```bash
./xo posts
```

Show fewer posts:

```bash
./xo posts --limit 5
```

Show a compact table:

```bash
./xo posts --table --limit 5
```

Rebuild normalized posts from saved raw responses after parser improvements:

```bash
./xo reparse
```

List captured media assets:

```bash
./xo media list
./xo media list --type photo
./xo media list --type video --pending
```

Download pending media assets:

```bash
./xo media download --limit 10
./xo media download --type photo --limit 20
./xo media download --type video --limit 5
```

Downloaded files are stored under:

```text
library/{username}/{post_id}/
```

Export normalized posts to JSONL:

```bash
uv run xoctopus export --format jsonl --output exports/posts.jsonl
```

Short form:

```bash
./xo export --format jsonl --output exports/posts.jsonl
```

Preview exported data:

```bash
head -n 5 exports/posts.jsonl
```

Each line is one JSON object from the `posts` table.

## 10. Tune Test Settings

For faster local testing, reduce delays in `config.toml`:

```toml
[rate_limit]
page_delay_min_seconds = 2
page_delay_max_seconds = 5
scroll_delay_min_seconds = 1
scroll_delay_max_seconds = 2
max_pages_per_run = 2
pause_on_429 = true
```

For normal use, keep conservative delays to reduce rate-limit risk.

Headless mode is available after login works:

```toml
[browser]
headless = true
```

You can also switch this from `Settings -> Browser collection` in the Web UI.
For debugging, login, and security challenges, keep `headless = false`.

If Playwright bundled Chromium is unavailable on your OS, use a system browser:

```toml
[browser]
headless = false
channel = "chrome"
executable_path = ""
```

If channel launch does not work, set the exact executable path:

```toml
[browser]
headless = false
channel = ""
executable_path = "/usr/bin/google-chrome"
```

Common executable paths:

```text
/usr/bin/google-chrome
/usr/bin/chromium
/usr/bin/chromium-browser
```

## 11. Status Meanings

Common command result statuses:

```text
success       collection finished without detected blocking errors
rate_limited  X returned HTTP 429 and pause_on_429 is enabled
parser_error  JSON was captured but could not be parsed into posts, or parsing failed
network_error browser navigation or Playwright failed
paused        required dependency or source configuration is missing/unsupported
```

If status is `parser_error` but `raw_events` increased, the raw JSON was still preserved in SQLite. The parser can be improved later without refetching the same response.

## 12. Troubleshooting

Missing config:

```bash
uv run xoctopus init
```

Playwright browser missing:

```bash
uv run playwright install chromium
```

On Ubuntu 26.04, use system Chrome/Chromium instead and set `browser.channel` or
`browser.executable_path` in `config.toml`.

No posts parsed:

```bash
uv run xoctopus status
```

If `raw_events` is `0`, the browser did not capture useful X JSON responses. Confirm you are logged in and the source page loads normally in the opened browser profile.

If `raw_events` is greater than `0` but `posts` is `0`, the parser likely needs a fixture update for the current X Web response shape.

Login expired:

```bash
uv run xoctopus login
```

Rate limited:

Increase delays in `config.toml`, reduce `max_pages_per_run`, and wait before retrying.
