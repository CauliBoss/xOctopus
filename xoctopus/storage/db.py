"""SQLite storage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from xoctopus.config import SourceConfig
from xoctopus.parser.schema import ParsedAuthor, ParsedPost, ParseResult

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )


def sync_sources(db_path: Path, sources: Iterable[SourceConfig]) -> None:
    now = utc_now()
    with connect(db_path) as conn:
        for source in sources:
            conn.execute(
                """
                INSERT INTO sources (
                    name, type, value, enabled, poll_interval_seconds, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    type = excluded.type,
                    value = excluded.value,
                    enabled = excluded.enabled,
                    poll_interval_seconds = excluded.poll_interval_seconds,
                    updated_at = excluded.updated_at
                """,
                (
                    source.name,
                    source.type,
                    source.value,
                    int(source.enabled),
                    source.poll_interval_seconds,
                    now,
                    now,
                ),
            )


def list_sources(db_path: Path) -> list[sqlite3.Row]:
    with connect(db_path) as conn:
        return list(conn.execute("SELECT * FROM sources ORDER BY name"))


def list_recent_fetch_runs(db_path: Path, limit: int = 5) -> list[sqlite3.Row]:
    with connect(db_path) as conn:
        return list(
            conn.execute(
                """
                SELECT
                    fetch_runs.id,
                    sources.name AS source_name,
                    fetch_runs.status,
                    fetch_runs.raw_event_count,
                    fetch_runs.post_count,
                    fetch_runs.new_post_count,
                    fetch_runs.error,
                    fetch_runs.finished_at
                FROM fetch_runs
                LEFT JOIN sources ON sources.id = fetch_runs.source_id
                ORDER BY fetch_runs.id DESC
                LIMIT ?
                """,
                (limit,),
            )
        )


def list_posts(
    db_path: Path,
    limit: int = 20,
    *,
    username: str | None = None,
    keyword: str | None = None,
    has_media: bool = False,
) -> list[sqlite3.Row]:
    conditions = []
    params: list[str | int] = []
    if username:
        conditions.append("LOWER(COALESCE(posts.username, authors.username, '')) = LOWER(?)")
        params.append(username)
    if keyword:
        conditions.append("posts.text LIKE ?")
        params.append(f"%{keyword}%")
    if has_media:
        conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM media_assets
                WHERE media_assets.post_id = posts.id
            )
            """
        )
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with connect(db_path) as conn:
        return list(
            conn.execute(
                f"""
                SELECT
                    posts.x_post_id,
                    COALESCE(posts.username, authors.username) AS username,
                    posts.text,
                    posts.created_at,
                    posts.like_count,
                    posts.repost_count,
                    posts.reply_count,
                    posts.quote_count,
                    posts.bookmark_count,
                    posts.view_count,
                    posts.urls_json,
                    posts.hashtags_json,
                    posts.media_json,
                    (
                        SELECT COUNT(*)
                        FROM media_assets
                        WHERE media_assets.post_id = posts.id
                    ) AS media_count,
                    posts.first_seen_at
                FROM posts
                LEFT JOIN authors ON authors.id = posts.author_id
                {where_sql}
                ORDER BY posts.id DESC
                LIMIT ?
                """,
                params,
            )
        )


def list_posts_with_media(
    db_path: Path,
    limit: int = 20,
    *,
    username: str | None = None,
    keyword: str | None = None,
    has_media: bool = False,
) -> list[dict]:
    posts = [
        dict(row)
        for row in list_posts(
            db_path,
            limit=limit,
            username=username,
            keyword=keyword,
            has_media=has_media,
        )
    ]
    if not posts:
        return []
    post_ids = [post["x_post_id"] for post in posts]
    placeholders = ", ".join("?" for _ in post_ids)
    with connect(db_path) as conn:
        media_rows = list(
            conn.execute(
                f"""
                SELECT
                    media_assets.*,
                    posts.x_post_id,
                    COALESCE(posts.username, authors.username) AS username
                FROM media_assets
                JOIN posts ON posts.id = media_assets.post_id
                LEFT JOIN authors ON authors.id = posts.author_id
                WHERE posts.x_post_id IN ({placeholders})
                ORDER BY media_assets.id
                """,
                post_ids,
            )
        )
    media_by_post: dict[str, list[dict]] = {post_id: [] for post_id in post_ids}
    for row in media_rows:
        media_by_post[row["x_post_id"]].append(dict(row))
    for post in posts:
        post["media_assets"] = media_by_post.get(post["x_post_id"], [])
    return posts


def list_media_assets(
    db_path: Path,
    *,
    limit: int = 50,
    media_type: str | None = None,
    pending_only: bool = False,
) -> list[sqlite3.Row]:
    conditions = []
    params: list[str | int] = []
    if media_type:
        conditions.append("media_assets.media_type = ?")
        params.append(media_type)
    if pending_only:
        conditions.append("media_assets.download_status != 'downloaded'")
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with connect(db_path) as conn:
        return list(
            conn.execute(
                f"""
                SELECT
                    media_assets.*,
                    posts.x_post_id,
                    COALESCE(posts.username, authors.username) AS username
                FROM media_assets
                JOIN posts ON posts.id = media_assets.post_id
                LEFT JOIN authors ON authors.id = posts.author_id
                {where_sql}
                ORDER BY media_assets.id DESC
                LIMIT ?
                """,
                params,
            )
        )


def mark_media_downloaded(db_path: Path, media_id: int, local_path: Path) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE media_assets
            SET local_path = ?, download_status = 'downloaded', error = NULL, updated_at = ?
            WHERE id = ?
            """,
            (str(local_path), utc_now(), media_id),
        )


def mark_media_failed(db_path: Path, media_id: int, error: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE media_assets
            SET download_status = 'failed', error = ?, updated_at = ?
            WHERE id = ?
            """,
            (error, utc_now(), media_id),
        )


def list_raw_events(db_path: Path) -> list[sqlite3.Row]:
    with connect(db_path) as conn:
        return list(conn.execute("SELECT id, body_json FROM raw_events ORDER BY id"))


def insert_raw_event(
    db_path: Path,
    *,
    source_id: int | None,
    collector: str,
    collector_version: str,
    page_url: str | None,
    request_url: str,
    status_code: int | None,
    body: dict,
) -> tuple[int | None, bool]:
    body_json = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    body_hash = sha256(body_json.encode("utf-8")).hexdigest()
    now = utc_now()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO raw_events (
                source_id, collector, collector_version, page_url, request_url, status_code,
                body_sha256, body_json, captured_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                collector,
                collector_version,
                page_url,
                request_url,
                status_code,
                body_hash,
                body_json,
                now,
            ),
        )
        if cursor.rowcount == 0:
            return None, False
        return int(cursor.lastrowid), True


def mark_raw_event_parsed(
    db_path: Path,
    raw_event_id: int,
    *,
    status: str,
    error: str | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE raw_events
            SET parsed_at = ?, parse_status = ?, parse_error = ?
            WHERE id = ?
            """,
            (utc_now(), status, error, raw_event_id),
        )


def upsert_parse_result(db_path: Path, result: ParseResult) -> tuple[int, int]:
    """Persist parsed authors and posts.

    Returns ``(post_count, new_post_count)``.
    """
    now = utc_now()
    with connect(db_path) as conn:
        author_ids = _upsert_authors(conn, result.authors, now)
        new_count = 0
        for post in result.posts:
            inserted = _upsert_post(conn, post, author_ids, now)
            if inserted:
                new_count += 1
    return len(result.posts), new_count


def insert_fetch_run(
    db_path: Path,
    *,
    source_id: int | None,
    collector: str,
    status: str,
    raw_event_count: int = 0,
    post_count: int = 0,
    new_post_count: int = 0,
    error: str | None = None,
) -> int:
    now = utc_now()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO fetch_runs (
                source_id, collector, started_at, finished_at, status, raw_event_count,
                post_count, new_post_count, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                collector,
                now,
                now,
                status,
                raw_event_count,
                post_count,
                new_post_count,
                error,
            ),
        )
        if source_id is not None:
            if status == "success":
                conn.execute(
                    """
                    UPDATE sources
                    SET last_success_at = ?, last_error = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, source_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE sources
                    SET last_error_at = ?, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, error or status, now, source_id),
                )
        return int(cursor.lastrowid)


def _upsert_authors(
    conn: sqlite3.Connection,
    authors: Iterable[ParsedAuthor],
    now: str,
) -> dict[str, int]:
    author_ids: dict[str, int] = {}
    for author in authors:
        raw_json = json.dumps(author.raw, ensure_ascii=False, sort_keys=True)
        conn.execute(
            """
            INSERT INTO authors (
                x_user_id, username, display_name, description, verified, followers_count,
                following_count, post_count, profile_image_url, raw_json, first_seen_at,
                last_seen_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(x_user_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                description = excluded.description,
                verified = excluded.verified,
                followers_count = excluded.followers_count,
                following_count = excluded.following_count,
                post_count = excluded.post_count,
                profile_image_url = excluded.profile_image_url,
                raw_json = excluded.raw_json,
                last_seen_at = excluded.last_seen_at,
                updated_at = excluded.updated_at
            """,
            (
                author.x_user_id,
                author.username,
                author.display_name,
                author.description,
                _bool_to_int(author.verified),
                author.followers_count,
                author.following_count,
                author.post_count,
                author.profile_image_url,
                raw_json,
                now,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT id FROM authors WHERE x_user_id = ?",
            (author.x_user_id,),
        ).fetchone()
        if row:
            author_ids[author.x_user_id] = int(row["id"])
    return author_ids


def _upsert_post(
    conn: sqlite3.Connection,
    post: ParsedPost,
    author_ids: dict[str, int],
    now: str,
) -> bool:
    author_id = author_ids.get(post.author_user_id or "")
    exists = conn.execute(
        "SELECT 1 FROM posts WHERE x_post_id = ?",
        (post.x_post_id,),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO posts (
            x_post_id, author_id, username, text, created_at, lang, conversation_id,
            reply_to_post_id, quote_post_id, repost_of_post_id, like_count, repost_count,
            reply_count, quote_count, bookmark_count, view_count, urls_json, hashtags_json,
            mentions_json, media_json, raw_json, first_seen_at, last_seen_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(x_post_id) DO UPDATE SET
            author_id = excluded.author_id,
            username = excluded.username,
            text = excluded.text,
            created_at = excluded.created_at,
            lang = excluded.lang,
            conversation_id = excluded.conversation_id,
            reply_to_post_id = excluded.reply_to_post_id,
            quote_post_id = excluded.quote_post_id,
            repost_of_post_id = excluded.repost_of_post_id,
            like_count = excluded.like_count,
            repost_count = excluded.repost_count,
            reply_count = excluded.reply_count,
            quote_count = excluded.quote_count,
            bookmark_count = excluded.bookmark_count,
            view_count = excluded.view_count,
            urls_json = excluded.urls_json,
            hashtags_json = excluded.hashtags_json,
            mentions_json = excluded.mentions_json,
            media_json = excluded.media_json,
            raw_json = excluded.raw_json,
            last_seen_at = excluded.last_seen_at,
            updated_at = excluded.updated_at
        """,
        (
            post.x_post_id,
            author_id,
            post.username,
            post.text,
            post.created_at,
            post.lang,
            post.conversation_id,
            post.reply_to_post_id,
            post.quote_post_id,
            post.repost_of_post_id,
            post.like_count,
            post.repost_count,
            post.reply_count,
            post.quote_count,
            post.bookmark_count,
            post.view_count,
            json.dumps(post.urls, ensure_ascii=False, sort_keys=True),
            json.dumps(post.hashtags, ensure_ascii=False, sort_keys=True),
            json.dumps(post.mentions, ensure_ascii=False, sort_keys=True),
            json.dumps(post.media, ensure_ascii=False, sort_keys=True),
            json.dumps(post.raw, ensure_ascii=False, sort_keys=True),
            now,
            now,
            now,
        ),
    )
    row = conn.execute(
        "SELECT id FROM posts WHERE x_post_id = ?",
        (post.x_post_id,),
    ).fetchone()
    if row:
        _upsert_media_assets(conn, int(row["id"]), post.media, now)
    return exists is None


def _upsert_media_assets(
    conn: sqlite3.Connection,
    post_id: int,
    media_items: Iterable[dict],
    now: str,
) -> None:
    for index, item in enumerate(media_items, start=1):
        media_key = str(item.get("media_key") or item.get("id_str") or f"{post_id}_{index}")
        media_type = str(item.get("type") or "")
        remote_url = _media_remote_url(item)
        preview_url = item.get("media_url_https")
        original_info = (
            item.get("original_info")
            if isinstance(item.get("original_info"), dict)
            else {}
        )
        width = _safe_int(original_info.get("width"))
        height = _safe_int(original_info.get("height"))
        video_info = item.get("video_info") if isinstance(item.get("video_info"), dict) else {}
        duration_ms = _safe_int(video_info.get("duration_millis"))
        conn.execute(
            """
            INSERT INTO media_assets (
                post_id, x_media_key, media_type, remote_url, preview_url, width, height,
                duration_ms, download_status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ON CONFLICT(x_media_key) DO UPDATE SET
                post_id = excluded.post_id,
                media_type = excluded.media_type,
                remote_url = excluded.remote_url,
                preview_url = excluded.preview_url,
                width = excluded.width,
                height = excluded.height,
                duration_ms = excluded.duration_ms,
                updated_at = excluded.updated_at
            """,
            (
                post_id,
                media_key,
                media_type,
                remote_url,
                preview_url,
                width,
                height,
                duration_ms,
                now,
                now,
            ),
        )


def _media_remote_url(item: dict) -> str | None:
    media_type = item.get("type")
    if media_type in {"video", "animated_gif"}:
        video_info = item.get("video_info") if isinstance(item.get("video_info"), dict) else {}
        variants = (
            video_info.get("variants")
            if isinstance(video_info.get("variants"), list)
            else []
        )
        mp4_variants = [
            variant
            for variant in variants
            if isinstance(variant, dict) and variant.get("content_type") == "video/mp4"
        ]
        if mp4_variants:
            best = max(mp4_variants, key=lambda variant: _safe_int(variant.get("bitrate")) or 0)
            return best.get("url")
    return item.get("media_url_https")


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)


def status_summary(db_path: Path) -> dict[str, int]:
    with connect(db_path) as conn:
        tables = ["sources", "raw_events", "authors", "posts", "media_assets", "fetch_runs"]
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }


def export_posts_jsonl(db_path: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with connect(db_path) as conn, output_path.open("w", encoding="utf-8") as fh:
        for row in conn.execute("SELECT * FROM posts ORDER BY created_at DESC, x_post_id DESC"):
            item = dict(row)
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1
    return count


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    value TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    poll_interval_seconds INTEGER NOT NULL DEFAULT 1800,
    last_seen_post_id TEXT,
    last_success_at TEXT,
    last_error_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    collector TEXT NOT NULL,
    collector_version TEXT NOT NULL,
    page_url TEXT,
    request_url TEXT NOT NULL,
    status_code INTEGER,
    body_sha256 TEXT NOT NULL UNIQUE,
    body_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    parsed_at TEXT,
    parse_status TEXT,
    parse_error TEXT
);

CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    x_user_id TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    verified INTEGER,
    followers_count INTEGER,
    following_count INTEGER,
    post_count INTEGER,
    profile_image_url TEXT,
    raw_json TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    x_post_id TEXT NOT NULL UNIQUE,
    author_id INTEGER REFERENCES authors(id) ON DELETE SET NULL,
    username TEXT,
    text TEXT,
    created_at TEXT,
    lang TEXT,
    conversation_id TEXT,
    reply_to_post_id TEXT,
    quote_post_id TEXT,
    repost_of_post_id TEXT,
    like_count INTEGER,
    repost_count INTEGER,
    reply_count INTEGER,
    quote_count INTEGER,
    bookmark_count INTEGER,
    view_count INTEGER,
    urls_json TEXT,
    hashtags_json TEXT,
    mentions_json TEXT,
    media_json TEXT,
    raw_json TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    x_media_key TEXT UNIQUE,
    media_type TEXT,
    remote_url TEXT,
    preview_url TEXT,
    local_path TEXT,
    width INTEGER,
    height INTEGER,
    duration_ms INTEGER,
    download_status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    collector TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    raw_event_count INTEGER NOT NULL DEFAULT 0,
    post_count INTEGER NOT NULL DEFAULT 0,
    new_post_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""
