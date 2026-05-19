"""FastAPI app factory for the local Web dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from xoctopus.config import DEFAULT_CONFIG_PATH, ConfigError, ensure_runtime_dirs, load_config
from xoctopus.source_config import (
    add_source,
    delete_source,
    make_source,
    set_browser_headless,
    set_source_enabled,
)
from xoctopus.storage import db
from xoctopus.web.i18n import normalize_lang, translator
from xoctopus.web.tasks import (
    Scheduler,
    TaskRunner,
    download_media_task,
    export_task,
    reparse_task,
    run_once_task,
    run_source_task,
)

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
runner = TaskRunner()
scheduler = Scheduler(runner, lambda: _load_ready_config())


def create_app() -> FastAPI:
    app = FastAPI(title="xOctopus", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
    Path("library").mkdir(parents=True, exist_ok=True)
    app.mount("/library", StaticFiles(directory="library"), name="library")

    @app.middleware("http")
    async def add_context(request: Request, call_next):
        request.state.config = _load_ready_config()
        return await call_next(request)

    @app.get("/")
    async def dashboard(request: Request):
        config = request.state.config
        return _render(
            request,
            "dashboard.html",
            active="dashboard",
            summary=db.status_summary(config.app.db_path),
            sources=db.list_sources(config.app.db_path),
            runs=db.list_recent_fetch_runs(config.app.db_path, limit=5),
            posts=db.list_posts_with_media(config.app.db_path, limit=3),
            media=db.list_media_assets(config.app.db_path, limit=5),
            pending_media=db.list_media_assets(
                config.app.db_path,
                limit=500,
                pending_only=True,
            ),
        )

    @app.get("/posts")
    async def posts(
        request: Request,
        limit: int = 25,
        view: str = "reader",
        username: str = "",
        keyword: str = "",
        has_media: bool = False,
    ):
        config = request.state.config
        view = view if view in {"reader", "archive"} else "reader"
        username = username.strip()
        keyword = keyword.strip()
        return _render(
            request,
            "posts.html",
            active="posts",
            posts=db.list_posts_with_media(
                config.app.db_path,
                limit=limit,
                username=username or None,
                keyword=keyword or None,
                has_media=has_media,
            ),
            limit=limit,
            view=view,
            username=username,
            keyword=keyword,
            has_media=has_media,
        )

    @app.get("/media")
    async def media(
        request: Request,
        limit: int = 50,
        type: str | None = None,
        pending: bool = False,
    ):
        config = request.state.config
        return _render(
            request,
            "media.html",
            active="media",
            media=db.list_media_assets(
                config.app.db_path,
                limit=limit,
                media_type=type or None,
                pending_only=pending,
            ),
            limit=limit,
            media_type=type or "",
            pending=pending,
        )

    @app.get("/sources")
    async def sources(request: Request):
        config = request.state.config
        return _render(
            request,
            "sources.html",
            active="sources",
            sources=db.list_sources(config.app.db_path),
            source_types=["user_timeline", "user_media", "search", "post", "list"],
            error=request.query_params.get("error", ""),
        )

    @app.post("/sources/add")
    async def add_source_route(
        value: str = Form(...),
        source_type: str = Form("user_timeline"),
        name: str = Form(""),
        poll_interval_seconds: int = Form(1800),
        enabled: bool = Form(False),
    ):
        try:
            source = make_source(
                value=value,
                source_type=source_type,
                name=name,
                enabled=enabled,
                poll_interval_seconds=poll_interval_seconds,
            )
            add_source(_config_path(), source)
        except ConfigError as exc:
            return RedirectResponse(f"/sources?error={quote(str(exc))}", status_code=303)
        return RedirectResponse("/sources", status_code=303)

    @app.post("/sources/enable")
    async def enable_source_route(name: str = Form(...)):
        set_source_enabled(_config_path(), name, True)
        return RedirectResponse("/sources", status_code=303)

    @app.post("/sources/disable")
    async def disable_source_route(name: str = Form(...)):
        set_source_enabled(_config_path(), name, False)
        return RedirectResponse("/sources", status_code=303)

    @app.post("/sources/delete")
    async def delete_source_route(name: str = Form(...)):
        delete_source(_config_path(), name)
        return RedirectResponse("/sources", status_code=303)

    @app.post("/sources/run")
    async def run_source_route(request: Request, name: str = Form(...)):
        runner.submit(f"Run {name}", run_source_task, request.state.config, name)
        return RedirectResponse("/sources", status_code=303)

    @app.get("/runs")
    async def runs(request: Request):
        config = request.state.config
        return _render(
            request,
            "runs.html",
            active="runs",
            runs=db.list_recent_fetch_runs(config.app.db_path, limit=25),
        )

    @app.get("/settings")
    async def settings(request: Request):
        return _render(
            request,
            "settings.html",
            active="settings",
            config=request.state.config,
            config_path=_config_path(),
        )

    @app.post("/settings/browser")
    async def update_browser_settings(headless: bool = Form(False)):
        set_browser_headless(_config_path(), headless)
        return RedirectResponse("/settings", status_code=303)

    @app.get("/set-language/{lang}")
    async def set_language(request: Request, lang: str):
        response = RedirectResponse(
            request.headers.get("referer") or "/",
            status_code=303,
        )
        response.set_cookie("xoctopus_lang", normalize_lang(lang), max_age=31536000)
        return response

    @app.post("/actions/{action}")
    async def action(request: Request, action: str):
        config = request.state.config
        actions = {
            "run-once": ("Run once", run_once_task, (config,)),
            "download-media": ("Download media", download_media_task, (config,)),
            "reparse": ("Reparse", reparse_task, (config,)),
            "export": ("Export JSONL", export_task, (config,)),
        }
        item = actions.get(action)
        if item:
            name, func, args = item
            runner.submit(name, func, *args)
        return RedirectResponse("/", status_code=303)

    @app.post("/scheduler/start")
    async def start_scheduler():
        scheduler.start()
        return RedirectResponse("/", status_code=303)

    @app.post("/scheduler/stop")
    async def stop_scheduler():
        scheduler.stop()
        return RedirectResponse("/", status_code=303)

    return app


def _render(request: Request, template: str, **context):
    lang = normalize_lang(request.cookies.get("xoctopus_lang"))
    context["request"] = request
    context["task"] = runner.state()
    context["scheduler"] = scheduler.state()
    context["lang"] = lang
    context["t"] = translator(lang)
    context["library_url"] = _library_url
    return templates.TemplateResponse(request, template, context)


def _load_ready_config():
    config = load_config(_config_path())
    ensure_runtime_dirs(config)
    db.init_db(config.app.db_path)
    db.sync_sources(config.app.db_path, config.sources)
    return config


def _config_path() -> Path:
    return Path(os.environ.get("XOCTOPUS_CONFIG", DEFAULT_CONFIG_PATH))


def _library_url(local_path: str | None) -> str:
    if not local_path:
        return ""
    path = Path(local_path)
    try:
        relative = path.relative_to("library")
    except ValueError:
        return ""
    return "/library/" + str(relative).replace("\\", "/")
