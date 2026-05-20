"""Configuration loading and defaults."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path("config.toml")
EXAMPLE_CONFIG_PATH = Path("config.example.toml")


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or validated."""


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    raw_dir: Path
    log_dir: Path
    log_level: str


@dataclass(frozen=True)
class BrowserConfig:
    headless: bool
    user_data_dir: Path
    channel: str
    executable_path: str
    slow_mo_ms: int
    navigation_timeout_ms: int


@dataclass(frozen=True)
class AuthConfig:
    mode: str
    cookies_file: Path
    cookies_format: str
    refresh_cookies: bool


@dataclass(frozen=True)
class AccountConfig:
    name: str
    auth_mode: str
    cookies_file: Path
    cookies_format: str
    refresh_cookies: bool


@dataclass(frozen=True)
class RateLimitConfig:
    page_delay_min_seconds: int
    page_delay_max_seconds: int
    scroll_delay_min_seconds: int
    scroll_delay_max_seconds: int
    max_pages_per_run: int
    pause_on_429: bool


@dataclass(frozen=True)
class HealthConfig:
    enabled: bool
    pause_on_auth_required: bool
    pause_on_challenge: bool
    pause_on_account_warning: bool
    backoff_on_rate_limit_seconds: int
    backoff_on_no_data_seconds: int
    max_consecutive_failures: int
    failure_backoff_seconds: int


@dataclass(frozen=True)
class MediaConfig:
    enabled: bool
    download_images: bool
    download_videos: bool
    downloader: str
    cookies_file: str


@dataclass(frozen=True)
class SourceConfig:
    name: str
    type: str
    value: str
    enabled: bool
    poll_interval_seconds: int
    account: str


@dataclass(frozen=True)
class Config:
    app: AppConfig
    browser: BrowserConfig
    auth: AuthConfig
    accounts: list[AccountConfig]
    rate_limit: RateLimitConfig
    health: HealthConfig
    media: MediaConfig
    sources: list[SourceConfig]


def init_config(path: Path = DEFAULT_CONFIG_PATH) -> bool:
    """Create a config file from the example if it does not exist.

    Returns True when a file was created.
    """
    if path.exists():
        return False
    if not EXAMPLE_CONFIG_PATH.exists():
        raise ConfigError(f"Missing {EXAMPLE_CONFIG_PATH}")
    shutil.copyfile(EXAMPLE_CONFIG_PATH, path)
    return True


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load and validate TOML configuration."""
    if not path.exists():
        raise ConfigError(f"Missing config file: {path}. Run `xoctopus init` first.")

    with path.open("rb") as fh:
        data = tomllib.load(fh)

    return parse_config(data)


def parse_config(data: dict[str, Any]) -> Config:
    app = data.get("app", {})
    browser = data.get("browser", {})
    auth = data.get("auth", {})
    accounts_raw = data.get("accounts", [])
    rate_limit = data.get("rate_limit", {})
    health = data.get("health", {})
    media = data.get("media", {})
    sources_raw = data.get("sources", [])

    auth_mode = _auth_mode(auth.get("mode", "profile"))
    cookies_format = _cookies_format(auth.get("cookies_format", "playwright"))
    default_auth = AuthConfig(
        mode=auth_mode,
        cookies_file=Path(auth.get("cookies_file", "data/cookies/x.cookies.json")),
        cookies_format=cookies_format,
        refresh_cookies=bool(auth.get("refresh_cookies", True)),
    )
    accounts = _parse_accounts(accounts_raw, default_auth)
    account_names = {account.name for account in accounts}
    fallback_account = accounts[0].name

    sources = []
    for item in sources_raw:
        source = SourceConfig(
            name=_required_str(item, "sources.name"),
            type=_required_str(item, "sources.type"),
            value=_required_str(item, "sources.value"),
            enabled=bool(item.get("enabled", True)),
            poll_interval_seconds=int(item.get("poll_interval_seconds", 1800)),
            account=str(item.get("account") or fallback_account).strip(),
        )
        if source.type not in {"user_timeline", "user_media", "search", "list", "post"}:
            raise ConfigError(f"Unsupported source type: {source.type}")
        if source.account not in account_names:
            raise ConfigError(f"Source {source.name} references unknown account: {source.account}")
        sources.append(source)

    return Config(
        app=AppConfig(
            db_path=Path(app.get("db_path", "data/xoctopus.sqlite3")),
            raw_dir=Path(app.get("raw_dir", "data/raw")),
            log_dir=Path(app.get("log_dir", "data/logs")),
            log_level=str(app.get("log_level", "INFO")),
        ),
        browser=BrowserConfig(
            headless=bool(browser.get("headless", False)),
            user_data_dir=Path(browser.get("user_data_dir", "data/browser-profile")),
            channel=str(browser.get("channel", "")),
            executable_path=str(browser.get("executable_path", "")),
            slow_mo_ms=int(browser.get("slow_mo_ms", 0)),
            navigation_timeout_ms=int(browser.get("navigation_timeout_ms", 60000)),
        ),
        auth=default_auth,
        accounts=accounts,
        rate_limit=RateLimitConfig(
            page_delay_min_seconds=int(rate_limit.get("page_delay_min_seconds", 20)),
            page_delay_max_seconds=int(rate_limit.get("page_delay_max_seconds", 90)),
            scroll_delay_min_seconds=int(rate_limit.get("scroll_delay_min_seconds", 3)),
            scroll_delay_max_seconds=int(rate_limit.get("scroll_delay_max_seconds", 8)),
            max_pages_per_run=int(rate_limit.get("max_pages_per_run", 20)),
            pause_on_429=bool(rate_limit.get("pause_on_429", True)),
        ),
        health=HealthConfig(
            enabled=bool(health.get("enabled", True)),
            pause_on_auth_required=bool(health.get("pause_on_auth_required", True)),
            pause_on_challenge=bool(health.get("pause_on_challenge", True)),
            pause_on_account_warning=bool(health.get("pause_on_account_warning", True)),
            backoff_on_rate_limit_seconds=int(
                health.get("backoff_on_rate_limit_seconds", 3600)
            ),
            backoff_on_no_data_seconds=int(health.get("backoff_on_no_data_seconds", 900)),
            max_consecutive_failures=int(health.get("max_consecutive_failures", 3)),
            failure_backoff_seconds=int(health.get("failure_backoff_seconds", 1800)),
        ),
        media=MediaConfig(
            enabled=bool(media.get("enabled", False)),
            download_images=bool(media.get("download_images", False)),
            download_videos=bool(media.get("download_videos", False)),
            downloader=str(media.get("downloader", "gallery-dl")),
            cookies_file=str(media.get("cookies_file", "")),
        ),
        sources=sources,
    )


def ensure_runtime_dirs(config: Config) -> None:
    config.app.db_path.parent.mkdir(parents=True, exist_ok=True)
    config.app.raw_dir.mkdir(parents=True, exist_ok=True)
    config.app.log_dir.mkdir(parents=True, exist_ok=True)
    config.browser.user_data_dir.mkdir(parents=True, exist_ok=True)
    config.auth.cookies_file.parent.mkdir(parents=True, exist_ok=True)
    for account in config.accounts:
        account.cookies_file.parent.mkdir(parents=True, exist_ok=True)
    Path("library").mkdir(parents=True, exist_ok=True)


def get_account(config: Config, name: str | None = None) -> AccountConfig:
    """Return a configured account by name, or the default account."""
    if name is None:
        return config.accounts[0]
    for account in config.accounts:
        if account.name == name:
            return account
    raise ConfigError(f"Unknown account: {name}")


def _parse_accounts(raw: Any, default_auth: AuthConfig) -> list[AccountConfig]:
    if not raw:
        return [
            AccountConfig(
                name="default",
                auth_mode=default_auth.mode,
                cookies_file=default_auth.cookies_file,
                cookies_format=default_auth.cookies_format,
                refresh_cookies=default_auth.refresh_cookies,
            )
        ]
    if not isinstance(raw, list):
        raise ConfigError("accounts must be a TOML array")
    accounts = []
    names = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ConfigError("accounts entries must be tables")
        name = _required_str(item, "accounts.name")
        if name in names:
            raise ConfigError(f"Duplicate account name: {name}")
        names.add(name)
        auth_mode = _auth_mode(item.get("auth_mode", item.get("mode", default_auth.mode)))
        cookies_format = _cookies_format(item.get("cookies_format", default_auth.cookies_format))
        accounts.append(
            AccountConfig(
                name=name,
                auth_mode=auth_mode,
                cookies_file=Path(item.get("cookies_file", f"data/accounts/{name}.cookies.json")),
                cookies_format=cookies_format,
                refresh_cookies=bool(item.get("refresh_cookies", default_auth.refresh_cookies)),
            )
        )
    return accounts


def _auth_mode(value: Any) -> str:
    mode = str(value).strip().lower()
    if mode not in {"profile", "cookies"}:
        raise ConfigError(f"Unsupported auth mode: {mode}")
    return mode


def _cookies_format(value: Any) -> str:
    cookies_format = str(value).strip().lower()
    if cookies_format not in {"playwright", "netscape"}:
        raise ConfigError(f"Unsupported auth cookies format: {cookies_format}")
    return cookies_format


def _required_str(item: dict[str, Any], key: str) -> str:
    name = key.split(".")[-1]
    value = item.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing required config value: {key}")
    return value.strip()
