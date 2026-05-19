"""Tiny in-process task runner for the local Web UI."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread

from xoctopus.config import Config
from xoctopus.jobs.discover import run_once, run_source
from xoctopus.jobs.media_download import download_pending_media
from xoctopus.parser.x_timeline import parse_timeline_response
from xoctopus.storage import db


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass
class TaskState:
    name: str = ""
    status: str = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    message: str = ""
    error: str = ""


@dataclass
class SchedulerState:
    active: bool = False
    last_check_at: str | None = None
    next_run_at: str | None = None
    current_source: str = ""
    message: str = ""
    error: str = ""


class TaskRunner:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = Lock()
        self._future: Future | None = None
        self._state = TaskState()

    def state(self) -> TaskState:
        with self._lock:
            return TaskState(**self._state.__dict__)

    def submit(self, name: str, func, *args, **kwargs) -> bool:
        with self._lock:
            if self._future and not self._future.done():
                return False
            self._state = TaskState(name=name, status="running", started_at=utc_now())
            self._future = self._executor.submit(self._run, name, func, args, kwargs)
            return True

    def _run(self, name: str, func, args, kwargs) -> None:
        try:
            message = func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - defensive task boundary
            with self._lock:
                self._state.status = "failed"
                self._state.finished_at = utc_now()
                self._state.error = str(exc)
            return
        with self._lock:
            self._state.status = "success"
            self._state.finished_at = utc_now()
            self._state.message = str(message or f"{name} completed")
            self._state.error = ""


class Scheduler:
    def __init__(
        self,
        runner: TaskRunner,
        config_loader: Callable[[], Config],
        *,
        tick_seconds: int = 5,
    ) -> None:
        self._runner = runner
        self._config_loader = config_loader
        self._tick_seconds = tick_seconds
        self._lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._state = SchedulerState()

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()
            self._state = SchedulerState(active=True, message="scheduler_started")
            self._thread = Thread(target=self._loop, name="xoctopus-scheduler", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._state.active = False
            self._state.message = "scheduler_stopped"

    def state(self) -> SchedulerState:
        with self._lock:
            if self._thread and not self._thread.is_alive() and self._state.active:
                self._state.active = False
            return SchedulerState(**self._state.__dict__)

    def _loop(self) -> None:
        due_at: dict[str, datetime] = {}
        while not self._stop.is_set():
            try:
                config = self._config_loader()
                enabled = [source for source in config.sources if source.enabled]
                now = datetime.now(UTC).replace(microsecond=0)
                enabled_names = {source.name for source in enabled}
                due_at = {name: due for name, due in due_at.items() if name in enabled_names}
                for source in enabled:
                    due_at.setdefault(source.name, now)

                due_sources = sorted(
                    (source for source in enabled if due_at[source.name] <= now),
                    key=lambda source: due_at[source.name],
                )
                message = "scheduler_idle"
                current_source = ""
                if due_sources:
                    source = due_sources[0]
                    submitted = self._runner.submit(
                        f"Scheduled {source.name}",
                        run_source_task,
                        config,
                        source.name,
                    )
                    if submitted:
                        current_source = source.name
                        due_at[source.name] = now + timedelta(
                            seconds=max(60, source.poll_interval_seconds)
                        )
                        message = "scheduled_run_started"
                    else:
                        message = "waiting_for_current_task"

                next_run = min(due_at.values(), default=None)
                self._set_state(
                    active=True,
                    last_check_at=now.isoformat(),
                    next_run_at=next_run.isoformat() if next_run else None,
                    current_source=current_source,
                    message=message,
                    error="",
                )
            except Exception as exc:  # pragma: no cover - defensive background boundary
                self._set_state(active=True, error=str(exc), message="scheduler_error")
            self._stop.wait(self._tick_seconds)
        self._set_state(active=False, message="scheduler_stopped")

    def _set_state(self, **values) -> None:
        with self._lock:
            for key, value in values.items():
                setattr(self._state, key, value)


def run_once_task(config: Config) -> str:
    result = run_once(config)
    return (
        f"run status={result.status}; raw={result.raw_event_count}; "
        f"posts={result.post_count}; new={result.new_post_count}"
    )


def run_source_task(config: Config, source_name: str) -> str:
    result = run_source(config, source_name)
    return (
        f"{source_name}: status={result.status}; raw={result.raw_event_count}; "
        f"posts={result.post_count}; new={result.new_post_count}"
    )


def download_media_task(config: Config, limit: int = 50) -> str:
    result = download_pending_media(config, limit=limit, output=Path("library"))
    return (
        f"downloaded={result.downloaded}; failed={result.failed}; "
        f"considered={result.considered}"
    )


def reparse_task(config: Config) -> str:
    raw_events = db.list_raw_events(config.app.db_path)
    total_posts = 0
    total_new = 0
    errors = 0
    for event in raw_events:
        try:
            parsed = parse_timeline_response(json.loads(event["body_json"]))
            post_count, new_count = db.upsert_parse_result(config.app.db_path, parsed)
            db.mark_raw_event_parsed(config.app.db_path, event["id"], status="success")
            total_posts += post_count
            total_new += new_count
        except Exception as exc:
            errors += 1
            db.mark_raw_event_parsed(
                config.app.db_path,
                event["id"],
                status="error",
                error=str(exc),
            )
    return f"raw={len(raw_events)}; posts={total_posts}; new={total_new}; errors={errors}"


def export_task(config: Config) -> str:
    output = Path("exports/posts.jsonl")
    count = db.export_posts_jsonl(config.app.db_path, output)
    return f"exported={count}; output={output}"
