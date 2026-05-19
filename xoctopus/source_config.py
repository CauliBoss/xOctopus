"""Helpers for editing configured sources in config.toml."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xoctopus.config import ConfigError, SourceConfig

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

SOURCE_TYPES = {"user_timeline", "user_media", "search", "list", "post"}


def add_source(path: Path, source: SourceConfig) -> None:
    data = _load_data(path)
    sources = list(data.get("sources", []))
    if any(item.get("name") == source.name for item in sources):
        raise ConfigError(f"Source already exists: {source.name}")
    sources.append(_source_to_dict(source))
    data["sources"] = sources
    _write_data(path, data)


def delete_source(path: Path, name: str) -> None:
    data = _load_data(path)
    sources = [item for item in data.get("sources", []) if item.get("name") != name]
    if len(sources) == len(data.get("sources", [])):
        raise ConfigError(f"Source not found: {name}")
    data["sources"] = sources
    _write_data(path, data)


def set_source_enabled(path: Path, name: str, enabled: bool) -> None:
    data = _load_data(path)
    found = False
    sources = []
    for item in data.get("sources", []):
        item = dict(item)
        if item.get("name") == name:
            item["enabled"] = enabled
            found = True
        sources.append(item)
    if not found:
        raise ConfigError(f"Source not found: {name}")
    data["sources"] = sources
    _write_data(path, data)


def set_browser_headless(path: Path, headless: bool) -> None:
    data = _load_data(path)
    browser = dict(data.get("browser", {}))
    browser["headless"] = headless
    data["browser"] = browser
    _write_data(path, data)


def make_source(
    *,
    value: str,
    source_type: str = "user_timeline",
    name: str = "",
    enabled: bool = True,
    poll_interval_seconds: int = 1800,
) -> SourceConfig:
    source_type = _normalize_source_type(source_type)
    value = value.strip()
    if not value:
        raise ConfigError("Source value is required.")
    if not name.strip():
        name = default_source_name(source_type, value)
    if poll_interval_seconds < 60:
        raise ConfigError("Poll interval must be at least 60 seconds.")
    return SourceConfig(
        name=_safe_name(name),
        type=source_type,
        value=value.lstrip("@") if source_type in {"user_timeline", "user_media"} else value,
        enabled=enabled,
        poll_interval_seconds=poll_interval_seconds,
    )


def default_source_name(source_type: str, value: str) -> str:
    safe = _safe_name(value)
    if source_type == "user_timeline":
        return f"{safe}_timeline"
    if source_type == "user_media":
        return f"{safe}_media"
    return f"{source_type}_{safe[:40]}"


def _normalize_source_type(source_type: str) -> str:
    aliases = {
        "user": "user_timeline",
        "timeline": "user_timeline",
        "media": "user_media",
        "user_timeline": "user_timeline",
        "user_media": "user_media",
        "search": "search",
        "list": "list",
        "post": "post",
    }
    try:
        return aliases[source_type]
    except KeyError as exc:
        raise ConfigError(f"Unsupported source type: {source_type}") from exc


def _safe_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in value.strip().lower())
    safe = "_".join(part for part in safe.split("_") if part)
    if not safe:
        raise ConfigError("Source name is required.")
    return safe[:64]


def _source_to_dict(source: SourceConfig) -> dict[str, Any]:
    return {
        "name": source.name,
        "type": source.type,
        "value": source.value,
        "enabled": source.enabled,
        "poll_interval_seconds": source.poll_interval_seconds,
    }


def _load_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Missing config file: {path}")
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _write_data(path: Path, data: dict[str, Any]) -> None:
    lines = []
    for section in ["app", "browser", "rate_limit", "media"]:
        if section in data:
            lines.extend(_format_table(section, data[section]))
            lines.append("")
    for source in data.get("sources", []):
        lines.append("[[sources]]")
        for key in ["name", "type", "value", "enabled", "poll_interval_seconds"]:
            if key in source:
                lines.append(f"{key} = {_toml_value(source[key])}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _format_table(name: str, values: dict[str, Any]) -> list[str]:
    lines = [f"[{name}]"]
    for key, value in values.items():
        lines.append(f"{key} = {_toml_value(value)}")
    return lines


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)
