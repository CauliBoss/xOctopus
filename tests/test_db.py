import json

from xoctopus.config import SourceConfig
from xoctopus.parser.schema import ParsedAuthor, ParsedPost, ParseResult
from xoctopus.storage import db


def test_init_db_and_sync_sources(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
    db.init_db(db_path)
    db.sync_sources(
        db_path,
        [
            SourceConfig(
                name="openai",
                type="user_timeline",
                value="OpenAI",
                enabled=True,
                poll_interval_seconds=1800,
            )
        ],
    )

    sources = db.list_sources(db_path)
    assert len(sources) == 1
    assert sources[0]["name"] == "openai"

    summary = db.status_summary(db_path)
    assert summary["sources"] == 1
    assert summary["posts"] == 0


def test_insert_fetch_run_updates_source_run_status(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
    db.init_db(db_path)
    db.sync_sources(
        db_path,
        [
            SourceConfig(
                name="openai",
                type="user_timeline",
                value="OpenAI",
                enabled=True,
                poll_interval_seconds=1800,
            )
        ],
    )
    source_id = db.list_sources(db_path)[0]["id"]

    db.insert_fetch_run(
        db_path,
        source_id=source_id,
        collector="playwright_x",
        status="success",
    )
    source = db.list_sources(db_path)[0]
    assert source["last_success_at"]
    assert source["last_error"] is None

    db.insert_fetch_run(
        db_path,
        source_id=source_id,
        collector="playwright_x",
        status="network_error",
        error="timeout",
    )
    source = db.list_sources(db_path)[0]
    assert source["last_error_at"]
    assert source["last_error"] == "timeout"


def test_export_posts_jsonl_empty(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
    output_path = tmp_path / "posts.jsonl"
    db.init_db(db_path)

    count = db.export_posts_jsonl(db_path, output_path)

    assert count == 0
    assert output_path.read_text(encoding="utf-8") == ""


def test_export_posts_jsonl_with_row(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
    output_path = tmp_path / "posts.jsonl"
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
            ("1", "OpenAI", "hello", now, now, now, now),
        )

    count = db.export_posts_jsonl(db_path, output_path)
    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert count == 1
    assert json.loads(lines[0])["x_post_id"] == "1"


def test_insert_raw_event_deduplicates_by_body(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
    db.init_db(db_path)

    first_id, first_inserted = db.insert_raw_event(
        db_path,
        source_id=None,
        collector="playwright_x",
        collector_version="test",
        page_url="https://x.com/OpenAI",
        request_url="https://x.com/i/api/graphql/test",
        status_code=200,
        body={"data": {"id": 1}},
    )
    second_id, second_inserted = db.insert_raw_event(
        db_path,
        source_id=None,
        collector="playwright_x",
        collector_version="test",
        page_url="https://x.com/OpenAI",
        request_url="https://x.com/i/api/graphql/test",
        status_code=200,
        body={"data": {"id": 1}},
    )

    assert first_id is not None
    assert first_inserted is True
    assert second_id is None
    assert second_inserted is False
    assert db.status_summary(db_path)["raw_events"] == 1


def test_upsert_parse_result_counts_only_new_posts(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
    db.init_db(db_path)
    result = ParseResult(
        authors=[ParsedAuthor(x_user_id="42", username="OpenAI", display_name="OpenAI")],
        posts=[
            ParsedPost(
                x_post_id="123",
                author_user_id="42",
                username="OpenAI",
                text="hello",
                created_at="Mon May 18 00:00:00 +0000 2026",
                like_count=1,
            )
        ],
    )

    first_total, first_new = db.upsert_parse_result(db_path, result)
    second_total, second_new = db.upsert_parse_result(db_path, result)

    assert (first_total, first_new) == (1, 1)
    assert (second_total, second_new) == (1, 0)
    assert db.status_summary(db_path)["authors"] == 1
    assert db.status_summary(db_path)["posts"] == 1


def test_list_posts_orders_recent_first(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
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
            ("1", "OpenAI", "older", "2026-01-01", "2026-01-01", now, now),
        )
        conn.execute(
            """
            INSERT INTO posts (
                x_post_id, username, text, created_at, first_seen_at, last_seen_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("2", "OpenAI", "newer", "2026-01-02", "2026-01-02", now, now),
        )

    posts = db.list_posts(db_path, limit=1)

    assert len(posts) == 1
    assert posts[0]["x_post_id"] == "2"


def test_upsert_parse_result_writes_media_assets(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
    db.init_db(db_path)
    result = ParseResult(
        posts=[
            ParsedPost(
                x_post_id="123",
                username="OpenAI",
                text="hello",
                created_at="2026-01-01",
                media=[
                    {
                        "media_key": "3_1",
                        "type": "photo",
                        "media_url_https": "https://pbs.twimg.com/media/test.jpg",
                        "original_info": {"width": 100, "height": 80},
                    }
                ],
            )
        ],
    )

    db.upsert_parse_result(db_path, result)
    media = db.list_media_assets(db_path)

    assert len(media) == 1
    assert media[0]["x_media_key"] == "3_1"
    assert media[0]["media_type"] == "photo"
    assert media[0]["remote_url"] == "https://pbs.twimg.com/media/test.jpg"


def test_list_posts_with_media_attaches_assets(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
    db.init_db(db_path)
    result = ParseResult(
        posts=[
            ParsedPost(
                x_post_id="123",
                username="OpenAI",
                text="hello",
                created_at="2026-01-01",
                media=[
                    {
                        "media_key": "3_1",
                        "type": "photo",
                        "media_url_https": "https://pbs.twimg.com/media/test.jpg",
                    }
                ],
            )
        ],
    )

    db.upsert_parse_result(db_path, result)
    posts = db.list_posts_with_media(db_path, limit=10)

    assert len(posts) == 1
    assert posts[0]["x_post_id"] == "123"
    assert posts[0]["media_assets"][0]["x_media_key"] == "3_1"


def test_list_posts_with_media_filters_posts(tmp_path):
    db_path = tmp_path / "xoctopus.sqlite3"
    db.init_db(db_path)
    now = db.utc_now()

    with db.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO posts (
                x_post_id, username, text, created_at, first_seen_at, last_seen_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("1", "OpenAI", "hello with image", "2026-01-01", now, now, now),
        )
        post_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO media_assets (
                post_id, x_media_key, media_type, remote_url, download_status, created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (post_id, "3_1", "photo", "https://pbs.twimg.com/media/test.jpg", "pending", now, now),
        )
        conn.execute(
            """
            INSERT INTO posts (
                x_post_id, username, text, created_at, first_seen_at, last_seen_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("2", "Other", "hello without image", "2026-01-02", now, now, now),
        )

    posts = db.list_posts_with_media(
        db_path,
        limit=10,
        username="openai",
        keyword="image",
        has_media=True,
    )

    assert len(posts) == 1
    assert posts[0]["x_post_id"] == "1"
    assert posts[0]["media_assets"][0]["x_media_key"] == "3_1"
