"""Command line interface."""

from __future__ import annotations

import json
import os
import time
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from xoctopus import __version__
from xoctopus.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    ensure_runtime_dirs,
    init_config,
    load_config,
)
from xoctopus.jobs.discover import collect_ad_hoc, run_once
from xoctopus.jobs.media_download import download_pending_media
from xoctopus.logging import setup_logging
from xoctopus.parser.x_timeline import parse_timeline_response
from xoctopus.storage import db

app = typer.Typer(help="Lightweight X Web content collector.")
source_app = typer.Typer(help="Manage configured sources.")
media_app = typer.Typer(help="Manage captured media assets.")
app.add_typer(source_app, name="source")
app.add_typer(media_app, name="media")
console = Console()


class ExportFormat(str, Enum):
    jsonl = "jsonl"


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"xOctopus {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """Lightweight X Web content collector."""


def _load_ready_config(config_path: Path):
    config = load_config(config_path)
    ensure_runtime_dirs(config)
    setup_logging(config.app.log_dir, config.app.log_level)
    db.init_db(config.app.db_path)
    db.sync_sources(config.app.db_path, config.sources)
    return config


@app.command()
def init(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Create config and runtime directories."""
    try:
        created = init_config(config)
        loaded = load_config(config)
        ensure_runtime_dirs(loaded)
        db.init_db(loaded.app.db_path)
        db.sync_sources(loaded.app.db_path, loaded.sources)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if created:
        console.print(f"[green]Created[/green] {config}")
    else:
        console.print(f"[yellow]Exists[/yellow] {config}")
    console.print(f"Database: {loaded.app.db_path}")


@app.command()
def login(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Open a persistent browser profile for manual X login."""
    loaded = _load_ready_config(config)
    from xoctopus.collectors.playwright_x import open_login_browser

    open_login_browser(loaded)


@app.command()
def collect(
    source_type: Annotated[str, typer.Argument(help="Source type: user, search, post, list.")],
    value: Annotated[str, typer.Argument(help="Username, query, post URL, or list URL.")],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Collect one ad-hoc source immediately."""
    loaded = _load_ready_config(config)
    result = collect_ad_hoc(loaded, source_type, value)
    console.print(
        f"Status: {result.status}; raw events: {result.raw_event_count}; "
        f"posts: {result.post_count}; new posts: {result.new_post_count}"
    )


@app.command()
def run(
    once: Annotated[bool, typer.Option("--once", help="Run one scheduled pass.")] = False,
    watch: Annotated[
        bool,
        typer.Option("--watch", help="Run a lightweight scheduler loop."),
    ] = False,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Run configured sources."""
    if not once and not watch:
        once = True

    loaded = _load_ready_config(config)
    if once:
        result = run_once(loaded)
        console.print(
            f"Status: {result.status}; raw events: {result.raw_event_count}; "
            f"posts: {result.post_count}; new posts: {result.new_post_count}"
        )
        return

    console.print("[green]Watching configured sources. Press Ctrl+C to stop.[/green]")
    try:
        while True:
            result = run_once(loaded)
            console.print(
                f"Status: {result.status}; raw events: {result.raw_event_count}; "
                f"posts: {result.post_count}; new posts: {result.new_post_count}"
            )
            enabled = [source for source in loaded.sources if source.enabled]
            sleep_seconds = min((s.poll_interval_seconds for s in enabled), default=1800)
            time.sleep(max(30, sleep_seconds))
    except KeyboardInterrupt:
        console.print("Stopped.")


@app.command()
def status(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Show local database status."""
    loaded = _load_ready_config(config)
    summary = db.status_summary(loaded.app.db_path)

    table = Table(title="xOctopus Status")
    table.add_column("Table")
    table.add_column("Rows", justify="right")
    for name, count in summary.items():
        table.add_row(name, str(count))
    console.print(table)

    sources = db.list_sources(loaded.app.db_path)
    source_table = Table(title="Sources")
    source_table.add_column("Name")
    source_table.add_column("Type")
    source_table.add_column("Value")
    source_table.add_column("Enabled")
    source_table.add_column("Last Error")
    for source in sources:
        source_table.add_row(
            source["name"],
            source["type"],
            source["value"],
            "yes" if source["enabled"] else "no",
            source["last_error"] or "",
        )
    console.print(source_table)

    runs = db.list_recent_fetch_runs(loaded.app.db_path)
    run_table = Table(title="Recent Runs")
    run_table.add_column("ID", justify="right")
    run_table.add_column("Source")
    run_table.add_column("Status")
    run_table.add_column("Raw", justify="right")
    run_table.add_column("Posts", justify="right")
    run_table.add_column("New", justify="right")
    run_table.add_column("Error")
    for run in runs:
        run_table.add_row(
            str(run["id"]),
            run["source_name"] or "",
            run["status"],
            str(run["raw_event_count"]),
            str(run["post_count"]),
            str(run["new_post_count"]),
            run["error"] or "",
        )
    console.print(run_table)


@app.command()
def export(
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("exports/posts.jsonl"),
    format: Annotated[ExportFormat, typer.Option("--format", "-f")] = ExportFormat.jsonl,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Export normalized posts."""
    loaded = _load_ready_config(config)
    if format is not ExportFormat.jsonl:
        raise typer.BadParameter("Only jsonl export is currently supported.")
    count = db.export_posts_jsonl(loaded.app.db_path, output)
    console.print(f"Exported {count} posts to {output}")


@app.command()
def posts(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of posts to show.")] = 20,
    table: Annotated[
        bool,
        typer.Option("--table", "-t", help="Show a compact table instead of cards."),
    ] = False,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Show recently collected posts in a readable format."""
    loaded = _load_ready_config(config)
    rows = db.list_posts(loaded.app.db_path, limit=limit)
    if not rows:
        console.print("No posts found. Run `./xo run --once` first.")
        return

    if table:
        _print_posts_table(rows)
        return

    for row in rows:
        console.print(_post_panel(row))


def _print_posts_table(rows) -> None:
    table = Table(title=f"Recent Posts ({len(rows)})")
    table.add_column("Time", overflow="fold", max_width=24)
    table.add_column("User", overflow="fold", max_width=18)
    table.add_column("Text", overflow="fold", max_width=72)
    table.add_column("Stats", overflow="fold", max_width=24)
    table.add_column("URL", overflow="fold", max_width=42)
    for row in rows:
        table.add_row(
            row["created_at"] or "",
            f"@{row['username']}" if row["username"] else "",
            _clean_text(row["text"], limit=220),
            _post_stats(row),
            _post_url(row),
        )
    console.print(table)


@app.command()
def reparse(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Reparse saved raw responses into normalized posts."""
    loaded = _load_ready_config(config)
    raw_events = db.list_raw_events(loaded.app.db_path)
    total_posts = 0
    total_new = 0
    errors = 0
    for event in raw_events:
        try:
            parsed = parse_timeline_response(json.loads(event["body_json"]))
            post_count, new_count = db.upsert_parse_result(loaded.app.db_path, parsed)
            db.mark_raw_event_parsed(loaded.app.db_path, event["id"], status="success")
            total_posts += post_count
            total_new += new_count
        except Exception as exc:
            errors += 1
            db.mark_raw_event_parsed(
                loaded.app.db_path,
                event["id"],
                status="error",
                error=str(exc),
            )
    console.print(
        f"Reparsed {len(raw_events)} raw events; posts: {total_posts}; "
        f"new posts: {total_new}; errors: {errors}"
    )


@source_app.command("list")
def source_list(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """List configured sources synced into the database."""
    loaded = _load_ready_config(config)
    sources = db.list_sources(loaded.app.db_path)
    table = Table(title="Sources")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Value")
    table.add_column("Enabled")
    for source in sources:
        table.add_row(
            source["name"],
            source["type"],
            source["value"],
            "yes" if source["enabled"] else "no",
        )
    console.print(table)


@source_app.command("add")
def source_add(
    source_type: Annotated[str, typer.Argument(help="user, media, search, list, or post.")],
    value: Annotated[str, typer.Argument(help="Username, query, or URL.")],
) -> None:
    """Print a config snippet for a new source.

    This keeps config edits explicit for the MVP instead of rewriting TOML.
    """
    mapped = _map_source_type(source_type)
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in value).strip("_").lower()
    name = f"{mapped}_{safe_name[:40]}" if safe_name else mapped
    console.print("Add this to config.toml:")
    snippet = f"""
[[sources]]
name = "{name}"
type = "{mapped}"
value = "{value}"
enabled = true
poll_interval_seconds = 1800
""".strip()
    console.print(snippet, markup=False)


def _map_source_type(source_type: str) -> str:
    aliases = {
        "user": "user_timeline",
        "timeline": "user_timeline",
        "user_timeline": "user_timeline",
        "media": "user_media",
        "user_media": "user_media",
        "search": "search",
        "list": "list",
        "post": "post",
    }
    try:
        return aliases[source_type]
    except KeyError as exc:
        raise typer.BadParameter(f"Unsupported source type: {source_type}") from exc


def _post_panel(row) -> Panel:
    lines = [
        f"User: @{row['username']}" if row["username"] else "User:",
        f"Time: {row['created_at'] or ''}",
        f"URL:  {_post_url(row)}",
        f"Stats: {_post_stats(row)}",
    ]
    hashtags = _json_value(row["hashtags_json"])
    urls = _json_value(row["urls_json"])
    media = _json_value(row["media_json"]) or []
    if row["media_count"]:
        lines.append("Media: " + _media_summary(media))
        preview_urls = [
            item.get("media_url_https")
            for item in media
            if isinstance(item, dict) and item.get("media_url_https")
        ]
        if preview_urls:
            lines.append("Preview: " + preview_urls[0])
    if hashtags:
        lines.append("Tags: " + ", ".join(f"#{tag}" for tag in hashtags))
    if urls:
        expanded = [
            item.get("expanded_url") or item.get("url")
            for item in urls
            if isinstance(item, dict)
        ]
        expanded = [url for url in expanded if url]
        if expanded:
            lines.append("Links: " + ", ".join(expanded[:3]))
    lines.extend(["", row["text"] or ""])
    return Panel("\n".join(lines), title=row["x_post_id"], expand=False)


def _post_stats(row) -> str:
    return " ".join(
        [
            f"reply:{row['reply_count'] or 0}",
            f"repost:{row['repost_count'] or 0}",
            f"like:{row['like_count'] or 0}",
            f"view:{row['view_count'] or 0}",
        ]
    )


def _post_url(row) -> str:
    username = row["username"] or "i"
    return f"https://x.com/{username}/status/{row['x_post_id']}"


def _media_summary(media: list) -> str:
    counts: dict[str, int] = {}
    for item in media:
        if isinstance(item, dict):
            media_type = str(item.get("type") or "unknown")
            counts[media_type] = counts.get(media_type, 0) + 1
    if not counts:
        return "yes"
    return ", ".join(f"{count} {name}" for name, count in sorted(counts.items()))


def _clean_text(value: str | None, *, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _json_value(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


@media_app.command("list")
def media_list(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of assets to show.")] = 50,
    media_type: Annotated[
        str | None,
        typer.Option("--type", help="photo, video, animated_gif"),
    ] = None,
    pending: Annotated[
        bool,
        typer.Option("--pending", help="Only show not-downloaded assets."),
    ] = False,
    table: Annotated[
        bool,
        typer.Option("--table", "-t", help="Show a compact table instead of cards."),
    ] = False,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """List captured media assets."""
    loaded = _load_ready_config(config)
    rows = db.list_media_assets(
        loaded.app.db_path,
        limit=limit,
        media_type=media_type,
        pending_only=pending,
    )
    if not rows:
        console.print("No media assets found.")
        return
    if not table:
        for row in rows:
            console.print(_media_panel(row))
        return

    table = Table(title=f"Media Assets ({len(rows)})")
    table.add_column("ID", justify="right")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("User")
    table.add_column("Post")
    table.add_column("Size")
    table.add_column("Remote URL", overflow="fold", max_width=64)
    table.add_column("Local Path", overflow="fold", max_width=36)
    for row in rows:
        table.add_row(
            str(row["id"]),
            row["media_type"] or "",
            row["download_status"],
            f"@{row['username']}" if row["username"] else "",
            row["x_post_id"],
            _media_size(row),
            row["remote_url"] or row["preview_url"] or "",
            row["local_path"] or "",
        )
    console.print(table)


@media_app.command("download")
def media_download(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of assets to download.")] = 20,
    media_type: Annotated[
        str | None,
        typer.Option("--type", help="photo, video, animated_gif"),
    ] = None,
    output: Annotated[Path, typer.Option("--output", "-o", help="Download root directory.")] = Path(
        "library"
    ),
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Download captured media assets."""
    loaded = _load_ready_config(config)
    result = download_pending_media(
        loaded,
        limit=limit,
        media_type=media_type,
        output=output,
    )
    console.print(
        f"Downloaded {result.downloaded}; failed {result.failed}; "
        f"considered {result.considered}"
    )


def _media_size(row) -> str:
    if row["width"] and row["height"]:
        return f"{row['width']}x{row['height']}"
    return ""


def _media_panel(row) -> Panel:
    lines = [
        f"Type:   {row['media_type'] or ''}",
        f"Status: {row['download_status']}",
        f"User:   @{row['username']}" if row["username"] else "User:",
        f"Post:   https://x.com/{row['username'] or 'i'}/status/{row['x_post_id']}",
        f"Size:   {_media_size(row)}",
        f"Remote: {row['remote_url'] or row['preview_url'] or ''}",
    ]
    if row["preview_url"] and row["preview_url"] != row["remote_url"]:
        lines.append(f"Preview: {row['preview_url']}")
    if row["local_path"]:
        lines.append(f"Local:  {row['local_path']}")
    if row["error"]:
        lines.append(f"Error:  {row['error']}")
    return Panel("\n".join(lines), title=f"media {row['id']}", expand=False)


@app.command()
def web(
    host: Annotated[str, typer.Option("--host", help="Host to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Port to bind.")] = 8787,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Config path."),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Run the local Web dashboard."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Web dependencies are missing. Run `uv sync --extra web`.") from exc

    os.environ["XOCTOPUS_CONFIG"] = str(config)
    console.print(f"Starting xOctopus Web at http://{host}:{port}")
    uvicorn.run(
        "xoctopus.web.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    app()
