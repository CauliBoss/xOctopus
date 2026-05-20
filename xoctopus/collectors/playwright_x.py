"""Playwright based X Web collector."""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from xoctopus.auth.cookies import X_COOKIE_URLS, load_cookies, save_playwright_cookies
from xoctopus.config import Config
from xoctopus.parser.x_timeline import parse_timeline_response
from xoctopus.storage import db

COLLECTOR_VERSION = "playwright_x_v1"


@dataclass(frozen=True)
class CollectorResult:
    status: str
    raw_event_count: int = 0
    post_count: int = 0
    new_post_count: int = 0
    error: str | None = None


def open_login_browser(config: Config) -> None:
    """Open a persistent browser profile for manual login.

    Login uses a regular Chrome/Chromium process when possible instead of a
    Playwright-controlled browser. Some login providers reject automated browser
    contexts, but a normal browser can still write the same persistent profile
    that later collection runs reuse.
    """
    command = _system_login_browser_command(config)
    if command:
        process = subprocess.Popen(command, env=_browser_env(config))  # noqa: S603
        print("Log in to X in the opened browser, then press Enter here to continue.")
        input()
        if process.poll() is None:
            process.terminate()
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("Playwright is not installed. Run `pip install -e .`.") from exc

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(config.browser.user_data_dir),
            headless=False,
            slow_mo=config.browser.slow_mo_ms,
            env=_browser_env(config),
            **_browser_launch_options(config),
        )
        page = context.new_page()
        page.goto("https://x.com/home", timeout=config.browser.navigation_timeout_ms)
        print("Log in to X in the opened browser, then press Enter here to close it.")
        input()
        context.close()


def collect_source(
    config: Config,
    source_type: str,
    value: str,
    *,
    source_id: int | None = None,
) -> CollectorResult:
    """Collect one source by capturing X Web JSON responses from a browser session."""
    try:
        target_url = source_url(source_type, value)
    except ValueError as exc:
        return CollectorResult(status="paused", error=str(exc))

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on local environment
        return CollectorResult(status="paused", error=f"playwright_not_installed: {exc}")

    captured: list[CapturedResponse] = []
    saw_rate_limit = False

    try:
        with sync_playwright() as pw:
            browser = None
            context = None
            try:
                if config.auth.mode == "cookies":
                    browser = pw.chromium.launch(
                        headless=config.browser.headless,
                        slow_mo=config.browser.slow_mo_ms,
                        env=_browser_env(config),
                        **_browser_launch_options(config),
                    )
                    context = browser.new_context()
                    context.add_cookies(
                        load_cookies(config.auth.cookies_file, config.auth.cookies_format)
                    )
                else:
                    context = pw.chromium.launch_persistent_context(
                        user_data_dir=str(config.browser.user_data_dir),
                        headless=config.browser.headless,
                        slow_mo=config.browser.slow_mo_ms,
                        env=_browser_env(config),
                        **_browser_launch_options(config),
                    )
                page = context.new_page()

                def on_response(response: Any) -> None:
                    nonlocal saw_rate_limit
                    if response.status == 429:
                        saw_rate_limit = True
                    if not _should_capture_response(response):
                        return
                    try:
                        body = response.json()
                    except Exception:
                        return
                    if isinstance(body, dict):
                        captured.append(
                            CapturedResponse(
                                page_url=page.url,
                                request_url=response.url,
                                status_code=response.status,
                                body=body,
                            )
                        )

                page.on("response", on_response)
                page.goto(target_url, timeout=config.browser.navigation_timeout_ms)
                _sleep_between(
                    config.rate_limit.page_delay_min_seconds,
                    config.rate_limit.page_delay_max_seconds,
                )
                for _ in range(max(1, config.rate_limit.max_pages_per_run)):
                    page.mouse.wheel(0, 2400)
                    _sleep_between(
                        config.rate_limit.scroll_delay_min_seconds,
                        config.rate_limit.scroll_delay_max_seconds,
                    )
                if config.auth.mode == "cookies" and config.auth.refresh_cookies:
                    save_playwright_cookies(config.auth.cookies_file, context.cookies(X_COOKIE_URLS))
            finally:
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()
    except PlaywrightTimeoutError as exc:
        return CollectorResult(status="network_error", error=f"navigation_timeout: {exc}")
    except PlaywrightError as exc:
        return CollectorResult(status="network_error", error=str(exc))
    except (OSError, ValueError) as exc:
        return CollectorResult(status="paused", error=f"cookie_auth_error: {exc}")

    if saw_rate_limit and config.rate_limit.pause_on_429:
        return CollectorResult(status="rate_limited", error="x_returned_http_429")
    if not captured:
        return CollectorResult(status="no_data", error="no_json_responses_captured")

    raw_event_count = 0
    post_count = 0
    new_post_count = 0
    parse_errors = []
    for item in captured:
        raw_event_id, inserted = db.insert_raw_event(
            config.app.db_path,
            source_id=source_id,
            collector="playwright_x",
            collector_version=COLLECTOR_VERSION,
            page_url=item.page_url,
            request_url=item.request_url,
            status_code=item.status_code,
            body=item.body,
        )
        if inserted:
            raw_event_count += 1
        try:
            parsed = parse_timeline_response(item.body)
            parsed_posts, parsed_new = db.upsert_parse_result(config.app.db_path, parsed)
            post_count += parsed_posts
            new_post_count += parsed_new
            if raw_event_id is not None:
                db.mark_raw_event_parsed(config.app.db_path, raw_event_id, status="success")
        except Exception as exc:
            parse_errors.append(str(exc))
            if raw_event_id is not None:
                db.mark_raw_event_parsed(
                    config.app.db_path,
                    raw_event_id,
                    status="error",
                    error=str(exc),
                )

    if parse_errors:
        return CollectorResult(
            status="parser_error",
            raw_event_count=raw_event_count,
            post_count=post_count,
            new_post_count=new_post_count,
            error="; ".join(parse_errors[:3]),
        )
    if captured and post_count == 0:
        return CollectorResult(
            status="parser_error",
            raw_event_count=raw_event_count,
            error="captured_json_but_no_posts_parsed",
        )
    return CollectorResult(
        status="success",
        raw_event_count=raw_event_count,
        post_count=post_count,
        new_post_count=new_post_count,
    )


@dataclass(frozen=True)
class CapturedResponse:
    page_url: str | None
    request_url: str
    status_code: int | None
    body: dict[str, Any]


def source_url(source_type: str, value: str) -> str:
    if source_type == "user_timeline":
        return f"https://x.com/{_clean_username(value)}"
    if source_type == "user_media":
        return f"https://x.com/{_clean_username(value)}/media"
    if source_type == "search":
        return f"https://x.com/search?q={quote(value)}&src=typed_query&f=live"
    if source_type in {"list", "post"} and value.startswith(("https://x.com/", "https://twitter.com/")):
        return value
    raise ValueError(f"Unsupported source type or value: {source_type}")


def _clean_username(value: str) -> str:
    return value.strip().lstrip("@")


def _should_capture_response(response: Any) -> bool:
    request = response.request
    resource_type = getattr(request, "resource_type", "")
    content_type = response.headers.get("content-type", "")
    url = response.url.lower()
    return (
        response.status < 400
        and resource_type in {"xhr", "fetch"}
        and ("json" in content_type or "/graphql/" in url or "/i/api/" in url)
        and ("x.com" in url or "twitter.com" in url)
    )


def _browser_launch_options(config: Config) -> dict[str, str]:
    if config.browser.executable_path:
        return {"executable_path": config.browser.executable_path}
    if config.browser.channel:
        return {"channel": config.browser.channel}
    return {}


def _system_login_browser_command(config: Config) -> list[str] | None:
    executable = (
        config.browser.executable_path
        or shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if not executable:
        return None
    return [
        executable,
        f"--user-data-dir={config.browser.user_data_dir.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "https://x.com/home",
    ]


def _browser_env(config: Config) -> dict[str, str]:
    data_home = config.app.db_path.parent / "xdg-data"
    config_home = config.app.db_path.parent / "xdg-config"
    data_home.mkdir(parents=True, exist_ok=True)
    config_home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "XDG_DATA_HOME": str(data_home),
        "XDG_CONFIG_HOME": str(config_home),
    })
    return env


def _sleep_between(min_seconds: int, max_seconds: int) -> None:
    if max_seconds <= 0:
        return
    lower = max(0, min_seconds)
    upper = max(lower, max_seconds)
    time.sleep(random.uniform(lower, upper))
