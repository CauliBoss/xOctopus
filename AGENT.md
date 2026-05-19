# xOctopus Agent Guide

## Project Goal

xOctopus is a lightweight, low-cost collector for X content where post information is the primary asset and media files are optional attachments.

The project intentionally avoids the official X API because of cost. The main approach is to collect X Web data through a real browser session, persist raw responses, normalize post data into a local database, and keep media downloading as a separate optional pipeline.

## Core Principles

1. Posts are the product. Media is secondary.
2. Preserve raw JSON for every captured response so parsers can be fixed later without refetching.
3. Prefer browser-session collection over brittle hand-written request replay.
4. Keep collectors replaceable. X Web internals change often.
5. Use conservative rate limits and explicit pause states when login, rate limit, captcha, or permission problems appear.
6. Do not build functionality for bypassing access controls, paywalls, private accounts, or platform restrictions.
7. Design for normal users, not only the original author. Defaults should be usable, commands should be discoverable, and errors should explain the next action.
8. Keep the project lightweight. Avoid always-on services, queues, external databases, or web frameworks until the core collector is stable.

## Product Shape

The first public version should be a polished local tool with both a CLI and a lightweight single-user Web dashboard. The CLI remains the automation-friendly interface. The Web dashboard is the normal user's control surface for browsing collected posts, managing monitored sources, starting/stopping scheduled collection, downloading media, and changing basic browser settings.

Primary user flows:

```bash
xoctopus init
xoctopus login
xoctopus source add user OpenAI
xoctopus source add search "(AI OR agent) -filter:replies"
xoctopus collect user OpenAI
xoctopus run --once
xoctopus run --watch
xoctopus status
xoctopus export --format jsonl --output exports/posts.jsonl
xoctopus web
```

The CLI should feel like a real tool:

- `xoctopus init` creates `config.toml`, `data/`, `library/`, and the SQLite database.
- `xoctopus login` opens a browser profile and waits for manual X login.
- `xoctopus run --once` performs one scheduled collection pass.
- `xoctopus run --watch` runs a lightweight scheduler loop.
- `xoctopus status` prints sources, recent runs, new post counts, and blocking errors.
- `xoctopus export` exports normalized posts without requiring users to inspect SQLite manually.
- `xoctopus web` starts the local Web dashboard.
- Commands should return meaningful exit codes for scripts and scheduled tasks.

The Web dashboard should feel like a small local operations console:

- Dashboard shows collection controls, task state, scheduler state, KPIs, recent posts, recent runs, and pending media.
- Sources manages monitored accounts/searches/lists/posts and their intervals.
- Posts shows reader/archive views and keeps media collapsed by default.
- Media shows pending/downloaded media and local file links.
- Runs shows recent collection history.
- Settings shows runtime paths and browser settings such as headless collection.

## GitHub-Ready Standards

This project should be built as an installable open-source package from the beginning.

Repository expectations:

```text
README.md
LICENSE
CHANGELOG.md
config.example.toml
pyproject.toml
.gitignore
AGENT.md
tests/
```

README should include:

- What the tool does and does not do.
- Install instructions.
- First-run workflow.
- Example source configuration.
- Common commands.
- Troubleshooting for login expired, 429, captcha, parser failures, and no data captured.
- Clear note that the project does not bypass access controls or automate X account actions.

Packaging expectations:

- Use `pyproject.toml`.
- Expose the console script as `xoctopus`.
- Keep runtime dependencies small.
- Separate optional media extras, for example `xoctopus[media]`.
- Pin only where necessary; avoid fragile dependency lock-in for library users.

Suggested dependency baseline:

```text
playwright
typer
rich
tomli; python_version < "3.11"
```

Optional dependencies:

```text
gallery-dl
yt-dlp
```

Developer dependencies:

```text
pytest
ruff
httpx
twine
```

## Usability Requirements

The tool should be normal-use friendly:

- Start with a visible browser by default for login and debugging.
- Support `--headless` only after login is known to work.
- Print short progress updates during collection.
- Store detailed logs under `data/logs/`.
- Never fail silently. If no posts are parsed, say whether no raw events were captured or parsing failed.
- Use clear paused states: `auth_required`, `rate_limited`, `captcha_required`, `parser_error`, `network_error`.
- Allow users to retry a single source without running the whole schedule.
- Use safe defaults: low scroll count, conservative delays, media download disabled.
- Make data portable: SQLite plus JSONL export.
- Keep config readable and copy-paste friendly.

## Recommended Architecture

```text
xOctopus/
├── xoctopus/
│   ├── cli.py
│   ├── config.py
│   ├── logging.py
│   ├── collectors/
│   │   ├── playwright_x.py
│   │   ├── guest_graphql.py
│   │   └── gallery_dl.py
│   ├── parser/
│   │   ├── schema.py
│   │   └── x_timeline.py
│   ├── storage/
│   │   ├── db.py
│   │   └── migrations/
│   ├── jobs/
│   │   ├── discover.py
│   │   ├── enrich.py
│   │   └── media_download.py
│   └── utils/
├── data/
│   ├── browser-profile/
│   ├── logs/
│   ├── raw/
│   └── xoctopus.sqlite3
├── library/
├── config.example.toml
├── pyproject.toml
└── AGENT.md
```

## Collection Strategy

### Primary Collector: Playwright X Web

Use Playwright with a persistent local browser profile:

```text
data/browser-profile/
```

First run opens a browser for manual login. Later runs reuse the stored session. The collector should visit configured X pages and intercept GraphQL/XHR responses from the browser instead of only scraping DOM text.

Supported source types:

- User timeline: `https://x.com/{username}`
- User media page: `https://x.com/{username}/media`
- Search page: `https://x.com/search?q=...&src=typed_query&f=live`
- List page, if added later
- Single post URL, if added later

Capture:

- Response URL
- HTTP status
- Request timestamp
- Response JSON body when parseable
- Source rule that triggered the request
- Browser page URL
- Collector version

### Fallback Collector: Guest GraphQL

The guest GraphQL collector may be used for public, low-volume fetches. It is less stable because internal query IDs, feature flags, and response shapes change. Treat it as optional and replaceable.

### Media Collector: gallery-dl / yt-dlp

Media downloading is not part of the post discovery path. It should consume rows from `media_assets` and can be disabled.

Use it for:

- Video downloads
- Image archival
- Cases where direct media URLs expire or need extractor support

Do not make cookies or gallery-dl a hard dependency for core post collection.

## Data Model

Use SQLite for MVP. Keep schemas migration-friendly so PostgreSQL can be added later.

### `sources`

Configured collection rules.

```text
id
name
type                 # user_timeline, user_media, search, list, post
value                # username, query, list URL, post URL
enabled
poll_interval_seconds
last_seen_post_id
last_success_at
last_error_at
last_error
created_at
updated_at
```

### `raw_events`

Append-only captured browser/API responses.

```text
id
source_id
collector
collector_version
page_url
request_url
status_code
body_sha256
body_json
captured_at
parsed_at
parse_status
parse_error
```

### `authors`

Normalized X account data.

```text
id
x_user_id
username
display_name
description
verified
followers_count
following_count
post_count
profile_image_url
raw_json
first_seen_at
last_seen_at
updated_at
```

### `posts`

Normalized post records. This is the most important table.

```text
id
x_post_id
author_id
username
text
created_at
lang
conversation_id
reply_to_post_id
quote_post_id
repost_of_post_id
like_count
repost_count
reply_count
quote_count
bookmark_count
view_count
urls_json
hashtags_json
mentions_json
media_json
raw_json
first_seen_at
last_seen_at
updated_at
```

### `media_assets`

Optional media metadata and download state.

```text
id
post_id
x_media_key
media_type          # photo, video, gif
remote_url
preview_url
local_path
width
height
duration_ms
download_status     # pending, skipped, downloaded, failed
error
created_at
updated_at
```

### `fetch_runs`

Operational tracking.

```text
id
source_id
collector
started_at
finished_at
status              # success, partial, failed, paused
raw_event_count
post_count
new_post_count
error
```

## Configuration Shape

```toml
[app]
db_path = "data/xoctopus.sqlite3"
raw_dir = "data/raw"
log_level = "INFO"

[browser]
headless = false
user_data_dir = "data/browser-profile"
slow_mo_ms = 0
navigation_timeout_ms = 60000

[rate_limit]
page_delay_min_seconds = 20
page_delay_max_seconds = 90
scroll_delay_min_seconds = 3
scroll_delay_max_seconds = 8
max_pages_per_run = 20
pause_on_429 = true

[media]
enabled = false
download_images = false
download_videos = false
downloader = "gallery-dl"
cookies_file = ""

[[sources]]
name = "openai_timeline"
type = "user_timeline"
value = "OpenAI"
enabled = true
poll_interval_seconds = 1800

[[sources]]
name = "ai_video_search"
type = "search"
value = "(AI OR agent) has:videos -filter:replies"
enabled = true
poll_interval_seconds = 1800
```

## Current Implementation Snapshot

Current version target: `0.2.0`.

Release state as of 2026-05-19:

- `0.2.0` is packaged and ready to upload.
- Built artifacts are expected at:
  - `dist/xoctopus-0.2.0.tar.gz`
  - `dist/xoctopus-0.2.0-py3-none-any.whl`
- Final local release checks passed:
  - `./xo --version`
  - `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev --extra web python -m pytest -q`
  - `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev --extra web python -m ruff check .`
  - `UV_CACHE_DIR=/tmp/uv-cache uv build`
  - `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev twine check dist/*`
- Latest verification on 2026-05-19:
  - `./xo --version` -> `xOctopus 0.2.0`
  - `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev --extra web python -m pytest -q` -> `18 passed`
  - `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev --extra web python -m ruff check .` -> passed
  - `UV_CACHE_DIR=/tmp/uv-cache uv build` -> rebuilt 0.2.0 sdist and wheel
  - `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev twine check dist/*` -> passed
- Actual upload is still pending because no Git remote, GitHub CLI, PyPI token,
  or Twine credentials are configured in the local environment.

Implemented:

- Installable Python package with `xoctopus` console script and local `./xo` helper.
- TOML config loading and runtime directory creation.
- SQLite schema for sources, raw events, authors, posts, media assets, and fetch runs.
- Playwright collector using a persistent browser profile.
- Manual login flow using a visible browser.
- System Chrome/Chromium support through `browser.channel` or `browser.executable_path`.
- CLI commands for init, login, collect, run, watch, status, posts, reparse, export, media list/download, and web.
- Web dashboard with Dashboard, Posts, Media, Sources, Runs, and Settings.
- Web route handlers use async ASGI endpoints; Web rendering tests use
  `httpx.ASGITransport` to avoid Starlette `TestClient` hangs seen in the local
  Python 3.13 sandbox.
- Web source add/enable/disable/delete/run actions.
- Web task runner for one foreground task at a time.
- Web in-process scheduler with start/stop controls.
- Web setting for `browser.headless`.
- Basic i18n switch for English and Chinese UI labels.
- Media metadata extraction and local media download workflow.
- JSONL export.
- Post filtering in the Web Posts page by username, keyword, and media presence.
- Tests for config, source config editing, database behavior, parser behavior,
  CLI version output, and basic Web Posts rendering.
- Release-ready README install notes, usage docs, changelog entry, package build,
  and `twine check` validation.

Known limitations:

- CLI `run --watch` and Web scheduler do not yet share one scheduling engine.
- CLI `run --watch` currently sleeps by the minimum enabled interval and then runs all enabled sources.
- Web scheduler keeps `next_run_at` in memory and recalculates from startup state, not persisted scheduler state.
- Web scheduler is single-process only and can duplicate work if multiple Web processes are started.
- Web task submission can fail because another task is running, but the UI does not yet show a clear "busy" notice.
- Config editing rewrites `config.toml` and does not preserve user comments or formatting.
- Collection status is still coarse: auth walls, challenge pages, no data, parser errors, and rate limits need clearer classification.
- No schema migration framework yet; `CREATE TABLE IF NOT EXISTS` is enough for MVP but not for public upgrades.
- Web UI has no auth because it is intended for `127.0.0.1` local use.
- PyPI/GitHub publication still requires configuring credentials and a remote.

## Temporary Claude Code Handoff

This project may be temporarily handed off to Claude Code using DeepSeek's
Anthropic-compatible endpoint. Treat this as a local developer workflow, not as
project runtime behavior.

Important security rule:

- Never write real API keys into tracked files.
- Never commit shell history, `.env`, local Claude settings, or debug logs that contain secrets.
- Use environment variables or an ignored local shell script for secrets.
- If a real key appears in a committed file, rotate the key before publishing.

Install Claude Code:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

Minimum runtime requirement:

```text
Node.js 18+
```

Use DeepSeek through the Anthropic-compatible API:

```bash
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"
export ANTHROPIC_MODEL="deepseekv4pro"
export ANTHROPIC_CUSTOM_MODEL_OPTION="deepseekv4pro"
export ANTHROPIC_CUSTOM_MODEL_OPTION_NAME="DeepSeek V4 Pro"
export ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION="DeepSeek V4 Pro via Anthropic-compatible API"
```

The real key must be provided outside this file:

```bash
export DEEPSEEK_API_KEY="replace-with-local-secret"
```

Do not use `ANTHROPIC_API_KEY` for this DeepSeek configuration. Claude Code
uses `ANTHROPIC_AUTH_TOKEN` for custom bearer-token gateways and
`ANTHROPIC_BASE_URL` to route requests through a compatible endpoint.

Start Claude Code from the project root:

```bash
cd /home/light/Project/xOctopus
./cc
```

Use the project launcher `./cc` instead of calling `claude` directly. The
launcher fixes the local npm global PATH, sets DeepSeek's Anthropic-compatible
endpoint, and reads `.env.claude` when present. Calling `claude` directly may
show Claude Code's normal account-login prompt if the environment variables are
not present in that shell.

The local `.env.claude` file should be a plain environment file, not a script:

```bash
DEEPSEEK_API_KEY="replace-with-local-secret"
```

Copy `.env.claude.example` to `.env.claude` and replace the placeholder locally.
Do not commit `.env.claude`.

Suggested first prompt for the temporary agent:

```text
Read AGENT.md, README.md, USAGE.md, and the current git status first.
This project is a local X content collector. Do not add evasion, captcha solving,
account rotation, proxy rotation, posting, liking, following, reposting, or DM
automation. Continue with Phase 1 in AGENT.md: unify CLI/Web scheduling around
one scheduling engine, preserve current tests, and add focused scheduler tests.
Do not commit local secrets, config.toml, data/, library/, exports/, or browser
profiles.
```

Recommended local helper script, ignored by git if named `.env` or stored
outside the repository:

```bash
#!/usr/bin/env bash
set -euo pipefail

export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="${DEEPSEEK_API_KEY:?set DEEPSEEK_API_KEY first}"
export ANTHROPIC_MODEL="deepseekv4pro"
export ANTHROPIC_CUSTOM_MODEL_OPTION="deepseekv4pro"
export ANTHROPIC_CUSTOM_MODEL_OPTION_NAME="DeepSeek V4 Pro"
export ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION="DeepSeek V4 Pro via Anthropic-compatible API"

exec /home/light/Project/xOctopus/cc "$@"
```

Before handing work back, Claude Code should run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev --extra web python -m ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev --extra web python -m pytest -q
```

## Next Development Plan

### Phase 1: Scheduling Correctness

Goal: make scheduled collection predictable and consistent across CLI and Web.

- Create a shared scheduler module under `xoctopus/jobs/scheduler.py`.
- Add a small `SourceSchedule` model with `source`, `last_run_at`, `next_run_at`, and `due` fields.
- Compute `next_run_at` from SQLite source state, not only from in-memory process state.
- Make CLI `run --watch` and Web Scheduler call the same scheduling functions.
- Change CLI `run --watch` so each source respects its own `poll_interval_seconds`.
- Add jitter support at the scheduler layer, not inside collector code.
- Add tests for mixed intervals, disabled sources, restart behavior, and busy task behavior.

Acceptance criteria:

- A source with `poll_interval_seconds = 1800` is not run every time a 300-second source is due.
- Restarting Web does not immediately re-run every source if recent successful runs are still inside their interval.
- CLI watch and Web scheduler produce the same due-source decisions for the same database state.

### Phase 2: Operational State and User Feedback

Goal: make failures understandable and actionable.

- Expand collection statuses:
  - `success`
  - `success_no_new`
  - `no_data`
  - `login_required`
  - `challenge_required`
  - `rate_limited`
  - `network_error`
  - `parser_error`
  - `busy`
- Detect obvious login/challenge pages after navigation by checking URL/title/body markers.
- Show Web notices when task submission is rejected because another task is running.
- Add a Scheduler detail section: current source, last check, next run, last message, last error.
- Show per-source next run time in Sources.
- Record `last_run_at` or derive it from `fetch_runs` reliably.

Acceptance criteria:

- When login expires, users see "login required" instead of only "no data captured".
- Clicking Run Once while another task is active shows a visible notice.
- Sources page explains when each enabled source will run next.

### Phase 3: Config Editing Safety

Goal: stop surprising users when Web edits `config.toml`.

- Replace manual TOML rewriting with `tomlkit` or move mutable source settings into SQLite.
- Preserve comments and section ordering when changing `browser.headless` or source settings.
- Add explicit backup behavior before Web rewrites config, for example `config.toml.bak`.
- Add a Settings note that explains which values are stored in TOML and which are stored in SQLite.

Recommended direction:

- Keep static runtime config in `config.toml`: app paths, browser path, rate limits, media settings.
- Move frequently edited monitored sources to SQLite once Web source management matures.
- Keep import/export commands for source definitions so users can still version their source list if needed.

Acceptance criteria:

- Toggling headless does not delete comments from `config.toml`.
- Adding/deleting a source does not unexpectedly reorder unrelated config sections.
- A failed config write never corrupts the only config file.

### Phase 4: Collector Robustness

Goal: make normal low-frequency collection more stable without adding evasion logic.

- Keep visible browser login as the default.
- Keep headless collection as an opt-in setting after login is stable.
- Reuse the persistent browser profile.
- Keep conservative delays and pause on rate limits.
- Add collector diagnostics: final page URL, page title, captured response count by endpoint.
- Add a small raw response fixture set for timeline, media tab, search, and post pages.
- Add parser regression tests from saved fixtures.

Non-goals:

- Do not implement captcha solving.
- Do not rotate accounts, proxies, device identities, or fingerprints.
- Do not automate posting, liking, following, reposting, or DMs.

Acceptance criteria:

- `no_data` runs include enough diagnostics to tell whether this is login, page change, or parser mismatch.
- Parser changes can be tested without hitting live X.

### Phase 5: GitHub Release Readiness

Goal: make the repository understandable and safe for outside users.

- Done: `.gitignore` covers `.venv/`, `data/`, `library/`, `exports/`, browser profiles, logs, local config, local env files, and build output.
- Done: `config.example.toml` is safe and complete for first-run usage.
- Done: `CHANGELOG.md` has `0.1.0` and `0.2.0` notes.
- Done: `docs/assets/web-dashboard-prototype.png` is included in the source distribution.
- Done: README states the Web UI is a local single-user dashboard.
- Done: README has a "What It Does Not Do" section near the top.
- Done: README and USAGE include development and user install paths.
- Done: release artifacts build and pass `twine check`.
- Remaining: add troubleshooting entries for Ubuntu 26.04 Playwright Chromium, system Chrome, X server/headless, login required, and no data captured.
- Remaining: configure a real Git remote and publishing credentials before upload.
- Add `CONTRIBUTING.md` only after issue labels and contribution expectations are clear.

Acceptance criteria:

- A fresh user can clone, install, login, add a source, run collection, view Web, and export posts from README alone.
- The repository does not encourage bypassing platform restrictions.
- Generated user data is not accidentally committed.
- `dist/xoctopus-0.2.0.tar.gz` and `dist/xoctopus-0.2.0-py3-none-any.whl`
  pass `twine check`.

## MVP Milestones

### Milestone 1: Skeleton

- Create Python package and CLI with `typer`.
- Add `pyproject.toml` and console script `xoctopus`.
- Add `xoctopus init`.
- Add TOML config loading.
- Add SQLite initialization and migrations.
- Add structured logging and user-readable terminal output.

### Milestone 2: Browser Login and Capture

- Launch Playwright with persistent `user_data_dir`.
- Provide `xoctopus login` command for manual login.
- Provide `xoctopus capture --source NAME`.
- Intercept JSON XHR/GraphQL responses and insert into `raw_events`.

### Milestone 3: Parser and Normalization

- Parse timeline/search raw responses into normalized posts.
- Upsert authors, posts, and media metadata.
- Keep `raw_json` on normalized rows.
- Track parser failures without discarding raw events.

### Milestone 4: Incremental Jobs

- Add `xoctopus run --once`.
- Add `xoctopus run --watch`.
- Add `xoctopus status`.
- Track `last_seen_post_id` and last successful run per source.
- Add conservative source scheduling.
- Stop or pause on 429, auth wall, captcha, or repeated parser failures.

### Milestone 5: Export and Public Usability

- Add `xoctopus export --format jsonl`.
- Add `xoctopus web` as a local single-user dashboard.
- Add focused README usage docs.
- Add `.gitignore`, `LICENSE`, and `CHANGELOG.md`.
- Add tests for config loading, database migration, raw event insertion, and parser fixtures.
- Add ruff configuration.

### Milestone 6: Optional Media

- Add media job queue from `media_assets`.
- Integrate gallery-dl or yt-dlp as optional external tools.
- Store local file path, download status, file size, and error.

### Milestone 7: Scheduler and Web Hardening

- Unify CLI watch and Web scheduler around one scheduling engine.
- Persist or derive next-run state from SQLite.
- Add busy notices and actionable failure states to Web.
- Preserve TOML comments or move mutable source state to SQLite.
- Add release-ready docs and ignore rules for generated local data.

## Implementation Notes

- Use `httpx` for lightweight direct requests only where appropriate.
- Use Playwright for X Web because it handles frontend bootstrapping and session state.
- Use `sqlite3` or SQLAlchemy Core. Avoid heavy service dependencies for MVP.
- Prefer `typer` for CLI and `rich` for readable terminal output.
- Use `orjson` only if performance requires it; standard `json` is fine initially.
- Store timestamps in UTC ISO 8601.
- Add unique constraints on `x_post_id`, `x_user_id`, `x_media_key`, and `body_sha256` where appropriate.
- Keep parsing defensive. X response shapes vary across timeline, search, profile, and media endpoints.
- Tests should use saved JSON fixtures, not live X network calls.
- Do not require Docker, Redis, PostgreSQL, or a web server for normal use.

## Safety and Compliance Boundaries

- Only collect content available to the logged-in browser session.
- Do not attempt to bypass private account restrictions, blocks, captchas, paywalls, or access controls.
- Do not automate posting, liking, reposting, following, or direct messaging.
- Do not implement credential stuffing, account rotation, captcha solving, or evasion logic.
- If X presents a login challenge, captcha, 429, or account warning, pause the job and require manual review.

## Why This Design

The official X API is the most stable option but can be expensive. Since this project avoids it, the next best tradeoff is browser-based collection with raw response capture. It keeps the system light and low-cost while preserving enough raw data to recover from parser breakage when X changes its frontend internals.
