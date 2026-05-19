"""Normalized parser schema types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParsedAuthor:
    x_user_id: str
    username: str
    display_name: str | None = None
    description: str | None = None
    verified: bool | None = None
    followers_count: int | None = None
    following_count: int | None = None
    post_count: int | None = None
    profile_image_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedPost:
    x_post_id: str
    username: str | None
    text: str | None
    created_at: str | None
    author_user_id: str | None = None
    lang: str | None = None
    conversation_id: str | None = None
    reply_to_post_id: str | None = None
    quote_post_id: str | None = None
    repost_of_post_id: str | None = None
    like_count: int | None = None
    repost_count: int | None = None
    reply_count: int | None = None
    quote_count: int | None = None
    bookmark_count: int | None = None
    view_count: int | None = None
    urls: list[dict[str, Any]] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    mentions: list[dict[str, Any]] = field(default_factory=list)
    media: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParseResult:
    authors: list[ParsedAuthor] = field(default_factory=list)
    posts: list[ParsedPost] = field(default_factory=list)
