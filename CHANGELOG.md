# Changelog

## 0.5.0

- Added session health and backoff tracking for accounts and sources.
- Added auth, challenge, account warning, rate limit, no-data, and repeated failure health handling.
- Added account/source status and resume commands for manual recovery.
- Added database health state for accounts and configured sources.
- Documented 会话健康与退避 behavior and boundaries.

## 0.4.0

- Added explicit multi-account configuration for user-owned browser profiles and cookie files.
- Added source-to-account binding so each source can declare which login account it uses.
- Added account CLI commands for listing, inspecting, importing cookies, and validating accounts.
- Updated collection progress output to show the account used by each source.
- Refined the README around local-first archiving, login modes, and future-safe account boundaries.

## 0.3.1

- Improved README guidance for `./xo`, cookie login, browser extension setup,
  no-GUI server usage, and Chinese quick-start instructions.

## 0.3.0

- Added cookie-file authentication for terminal-only and server deployments.
- Added auth CLI commands for cookie status, import, export, and login validation.
- Added a Chrome/Chromium cookie exporter extension for X/Twitter session cookies.
- Added per-source progress output for collection runs, with `--quiet` for final summaries only.
- Clarified CLI/no-web usage while keeping the local Web dashboard as an optional extra.

## 0.2.3

- Expanded the README with a Web-dashboard-first overview and screenshots for Dashboard, Posts, and Sources.

## 0.2.2

## 0.2.1

## 0.2.0

- Added the local FastAPI/Jinja Web dashboard with Dashboard, Posts, Media, Sources, Runs, and Settings pages.
- Added in-process Web actions for running collection, scheduled collection, media download, reparse, and JSONL export.
- Added browser-based X Web response capture with raw JSON persistence and conservative timeline/search parsing.
- Added SQLite storage for sources, raw events, authors, posts, media assets, and fetch runs.
- Added source management helpers, headless browser settings updates, post/media browsing, and JSONL export.
- Added optional media download flow from captured media assets into the local `library/` directory.
- Added bilingual English/Chinese Web UI labels.

## 0.1.0

- Initial project scaffold.
