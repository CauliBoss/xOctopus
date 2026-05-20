# Changelog

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
