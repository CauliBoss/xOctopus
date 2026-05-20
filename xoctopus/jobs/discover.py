"""Discovery jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from xoctopus.collectors.playwright_x import CollectorResult, collect_source
from xoctopus.config import Config, SourceConfig
from xoctopus.storage import db


@dataclass(frozen=True)
class JobResult:
    status: str
    raw_event_count: int = 0
    post_count: int = 0
    new_post_count: int = 0
    error: str | None = None


ProgressCallback = Callable[[str, SourceConfig, CollectorResult | None, int, int], None]


def collect_ad_hoc(config: Config, source_type: str, value: str) -> JobResult:
    mapped_type = _map_source_type(source_type)
    result = collect_source(config, mapped_type, value)
    _record_run(config, None, result)
    return _to_job_result(result)


def run_once(config: Config, progress: ProgressCallback | None = None) -> JobResult:
    enabled_sources = [source for source in config.sources if source.enabled]
    if not enabled_sources:
        result = JobResult(status="success")
        db.insert_fetch_run(
            config.app.db_path,
            source_id=None,
            collector="playwright_x",
            status=result.status,
        )
        return result

    total_raw = 0
    total_posts = 0
    total_new = 0
    errors = []
    final_status = "success"

    source_rows = {row["name"]: row for row in db.list_sources(config.app.db_path)}
    total_sources = len(enabled_sources)
    for index, source in enumerate(enabled_sources, start=1):
        if progress is not None:
            progress("start", source, None, index, total_sources)
        row = source_rows.get(source.name)
        result = collect_source(
            config,
            source.type,
            source.value,
            source_id=row["id"] if row else None,
        )
        _record_run(config, row["id"] if row else None, result)
        total_raw += result.raw_event_count
        total_posts += result.post_count
        total_new += result.new_post_count
        if result.status != "success":
            final_status = result.status
        if result.error:
            errors.append(f"{source.name}: {result.error}")
        if progress is not None:
            progress("finish", source, result, index, total_sources)

    return JobResult(
        status=final_status,
        raw_event_count=total_raw,
        post_count=total_posts,
        new_post_count=total_new,
        error="; ".join(errors) if errors else None,
    )


def run_source(config: Config, source_name: str) -> JobResult:
    source = next((item for item in config.sources if item.name == source_name), None)
    if source is None:
        return JobResult(status="paused", error=f"source_not_found: {source_name}")
    source_rows = {row["name"]: row for row in db.list_sources(config.app.db_path)}
    row = source_rows.get(source.name)
    result = collect_source(
        config,
        source.type,
        source.value,
        source_id=row["id"] if row else None,
    )
    _record_run(config, row["id"] if row else None, result)
    return _to_job_result(result)


def _record_run(config: Config, source_id: int | None, result: CollectorResult) -> None:
    db.insert_fetch_run(
        config.app.db_path,
        source_id=source_id,
        collector="playwright_x",
        status=result.status,
        raw_event_count=result.raw_event_count,
        post_count=result.post_count,
        new_post_count=result.new_post_count,
        error=result.error,
    )


def _to_job_result(result: CollectorResult) -> JobResult:
    return JobResult(
        status=result.status,
        raw_event_count=result.raw_event_count,
        post_count=result.post_count,
        new_post_count=result.new_post_count,
        error=result.error,
    )


def _map_source_type(source_type: str) -> str:
    aliases = {
        "user": "user_timeline",
        "timeline": "user_timeline",
        "media": "user_media",
        "search": "search",
        "list": "list",
        "post": "post",
        "user_timeline": "user_timeline",
        "user_media": "user_media",
    }
    if source_type not in aliases:
        raise ValueError(f"Unsupported source type: {source_type}")
    return aliases[source_type]
