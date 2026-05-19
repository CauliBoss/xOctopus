"""Media download jobs."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from xoctopus.config import Config
from xoctopus.storage import db


@dataclass(frozen=True)
class MediaDownloadResult:
    considered: int = 0
    downloaded: int = 0
    failed: int = 0


def download_pending_media(
    config: Config,
    *,
    limit: int = 20,
    media_type: str | None = None,
    output: Path = Path("library"),
) -> MediaDownloadResult:
    rows = db.list_media_assets(
        config.app.db_path,
        limit=limit,
        media_type=media_type,
        pending_only=True,
    )
    downloaded = 0
    failed = 0
    for row in rows:
        url = row["remote_url"] or row["preview_url"]
        if not url:
            db.mark_media_failed(config.app.db_path, row["id"], "missing_remote_url")
            failed += 1
            continue
        target = media_output_path(output, row, url)
        try:
            download_url(url, target)
            db.mark_media_downloaded(config.app.db_path, row["id"], target)
            downloaded += 1
        except Exception as exc:
            db.mark_media_failed(config.app.db_path, row["id"], str(exc))
            failed += 1
    return MediaDownloadResult(considered=len(rows), downloaded=downloaded, failed=failed)


def media_output_path(root: Path, row, url: str) -> Path:
    username = row["username"] or "unknown"
    suffix = media_suffix(url, row["media_type"])
    media_key = str(row["x_media_key"] or row["id"]).replace("/", "_")
    return root / username / row["x_post_id"] / f"{media_key}{suffix}"


def media_suffix(url: str, media_type: str | None) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix
    if suffix:
        return suffix
    if media_type in {"video", "animated_gif"}:
        return ".mp4"
    return ".jpg"


def download_url(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=60) as response, target.open("wb") as fh:
        shutil.copyfileobj(response, fh)
