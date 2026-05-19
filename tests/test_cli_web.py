import asyncio
from pathlib import Path

import httpx
from typer.testing import CliRunner

from xoctopus.cli import app
from xoctopus.storage import db
from xoctopus.web.app import create_app


def test_cli_version_command():
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "xOctopus 0.2.0" in result.output


def test_web_posts_page_renders_with_temp_config(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("XOCTOPUS_CONFIG", str(config_path))
    _insert_post(tmp_path / "xoctopus.sqlite3")

    response = asyncio.run(
        _get(
            "/posts",
            params={"username": "OpenAI", "keyword": "release"},
        )
    )

    assert response.status_code == 200
    assert "release notes" in response.text
    assert "OpenAI" in response.text


async def _get(path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, **kwargs)


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[app]
db_path = "{tmp_path / "xoctopus.sqlite3"}"
raw_dir = "{tmp_path / "raw"}"
log_dir = "{tmp_path / "logs"}"

[browser]
user_data_dir = "{tmp_path / "browser-profile"}"

[[sources]]
name = "openai_timeline"
type = "user_timeline"
value = "OpenAI"
enabled = true
poll_interval_seconds = 1800
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return config_path


def _insert_post(db_path: Path) -> None:
    db.init_db(db_path)
    now = db.utc_now()
    with db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO posts (
                x_post_id, username, text, created_at, first_seen_at, last_seen_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("1", "OpenAI", "release notes", "2026-01-01", now, now, now),
        )
