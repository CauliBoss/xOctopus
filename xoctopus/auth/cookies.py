"""Cookie file helpers for X browser sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xoctopus.config import Config

X_COOKIE_URLS = ["https://x.com", "https://twitter.com"]
X_COOKIE_DOMAINS = ("x.com", ".x.com", "twitter.com", ".twitter.com")
LIKELY_AUTH_COOKIE_NAMES = ("auth_token", "ct0", "twid")


@dataclass(frozen=True)
class CookieStatus:
    path: Path
    exists: bool
    count: int = 0
    domains: tuple[str, ...] = ()
    has_auth_token: bool = False
    has_ct0: bool = False
    has_twid: bool = False
    error: str | None = None

    @property
    def likely_logged_in(self) -> bool:
        return self.has_auth_token and self.has_ct0


def load_playwright_cookies(path: Path) -> list[dict[str, Any]]:
    """Load cookies in Playwright's JSON shape."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("cookie_file_must_contain_a_json_array")
    cookies = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("cookie_entries_must_be_objects")
        normalized = normalize_playwright_cookie(item)
        if _is_x_cookie(normalized):
            cookies.append(normalized)
    return cookies


def load_cookies(path: Path, cookie_format: str) -> list[dict[str, Any]]:
    """Load cookies from a supported file format."""
    normalized_format = cookie_format.strip().lower()
    if normalized_format == "playwright":
        return load_playwright_cookies(path)
    if normalized_format == "netscape":
        return load_netscape_cookies(path)
    raise ValueError(f"unsupported_cookie_format: {cookie_format}")


def save_playwright_cookies(path: Path, cookies: list[dict[str, Any]]) -> None:
    """Persist X/Twitter cookies in Playwright's JSON shape."""
    path.parent.mkdir(parents=True, exist_ok=True)
    filtered = [normalize_playwright_cookie(cookie) for cookie in cookies if _is_x_cookie(cookie)]
    with path.open("w", encoding="utf-8") as fh:
        json.dump(filtered, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def import_cookies(input_path: Path, output_path: Path, cookie_format: str) -> int:
    """Import cookies from a supported external format into Playwright JSON."""
    normalized_format = cookie_format.strip().lower()
    cookies = load_cookies(input_path, normalized_format)
    save_playwright_cookies(output_path, cookies)
    return len(cookies)


def cookie_status(path: Path) -> CookieStatus:
    """Return local cookie-file status without contacting X."""
    if not path.exists():
        return CookieStatus(path=path, exists=False)
    try:
        cookies = load_playwright_cookies(path)
    except Exception as exc:
        return CookieStatus(path=path, exists=True, error=str(exc))
    names = {str(cookie.get("name") or "") for cookie in cookies}
    domains = sorted({str(cookie.get("domain") or "") for cookie in cookies if cookie.get("domain")})
    return CookieStatus(
        path=path,
        exists=True,
        count=len(cookies),
        domains=tuple(domains),
        has_auth_token="auth_token" in names,
        has_ct0="ct0" in names,
        has_twid="twid" in names,
    )


def load_netscape_cookies(path: Path) -> list[dict[str, Any]]:
    """Load a Netscape cookies.txt file and convert it to Playwright cookies."""
    cookies = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            http_only = line.startswith("#HttpOnly_")
            if http_only:
                line = line.removeprefix("#HttpOnly_")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 7:
                raise ValueError(f"invalid_netscape_cookie_line:{line_number}")
            domain, _include_subdomains, path_value, secure, expires, name, value = parts
            cookie = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path_value or "/",
                "expires": _parse_expires(expires),
                "httpOnly": http_only,
                "secure": secure.upper() == "TRUE",
                "sameSite": "Lax",
            }
            if _is_x_cookie(cookie):
                cookies.append(normalize_playwright_cookie(cookie))
    return cookies


def normalize_playwright_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    """Normalize browser/extension cookie objects to Playwright-compatible JSON."""
    name = str(cookie.get("name") or "")
    value = str(cookie.get("value") or "")
    domain = str(cookie.get("domain") or "")
    path = str(cookie.get("path") or "/")
    if not name or not domain:
        raise ValueError("cookie_requires_name_and_domain")

    expires = cookie.get("expires", cookie.get("expirationDate", -1))
    normalized = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "expires": _parse_expires(expires),
        "httpOnly": bool(cookie.get("httpOnly", False)),
        "secure": bool(cookie.get("secure", True)),
        "sameSite": _normalize_same_site(cookie.get("sameSite")),
    }
    return normalized


def export_profile_cookies(config: Config, output_path: Path | None = None) -> int:
    """Export X cookies from the configured persistent browser profile."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("Playwright is not installed. Run `playwright install chromium`.") from exc

    from xoctopus.collectors.playwright_x import _browser_env, _browser_launch_options

    target = output_path or config.auth.cookies_file
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(config.browser.user_data_dir),
            headless=True,
            env=_browser_env(config),
            **_browser_launch_options(config),
        )
        cookies = context.cookies(X_COOKIE_URLS)
        context.close()
    save_playwright_cookies(target, cookies)
    return len([cookie for cookie in cookies if _is_x_cookie(cookie)])


def _is_x_cookie(cookie: dict[str, Any]) -> bool:
    domain = str(cookie.get("domain") or "").lower()
    bare = domain.lstrip(".")
    return bare in {"x.com", "twitter.com"} or bare.endswith(".x.com") or bare.endswith(".twitter.com")


def _normalize_same_site(value: Any) -> str:
    raw = str(value or "Lax")
    mapping = {
        "no_restriction": "None",
        "none": "None",
        "lax": "Lax",
        "strict": "Strict",
        "unspecified": "Lax",
    }
    return mapping.get(raw.lower(), raw if raw in {"Lax", "Strict", "None"} else "Lax")


def _parse_expires(value: Any) -> int:
    if value in {None, ""}:
        return -1
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return -1
    return parsed if parsed > 0 else -1
