"""Parser for common X Web GraphQL timeline/search responses."""

from __future__ import annotations

from typing import Any

from xoctopus.parser.schema import ParsedAuthor, ParsedPost, ParseResult


def parse_timeline_response(payload: dict[str, Any]) -> ParseResult:
    """Parse a captured X timeline/search response.

    X Web responses are deeply nested and change frequently. This parser keeps
    the contract intentionally forgiving: it walks the payload, recognizes tweet
    and user result nodes wherever they appear, and deduplicates by X ids.
    """
    authors: dict[str, ParsedAuthor] = {}
    posts: dict[str, ParsedPost] = {}

    for item in _walk_dicts(payload):
        user = _extract_user(item)
        if user:
            authors[user.x_user_id] = user

        post = _extract_post(item)
        if post:
            posts[post.x_post_id] = post
            legacy_user = item.get("user") if isinstance(item.get("user"), dict) else None
            if legacy_user:
                user = _extract_user(legacy_user)
                if user:
                    authors[user.x_user_id] = user

    return ParseResult(authors=list(authors.values()), posts=list(posts.values()))


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _extract_user(item: dict[str, Any]) -> ParsedAuthor | None:
    result = _unwrap_result(item)
    legacy = result.get("legacy") if isinstance(result.get("legacy"), dict) else {}
    rest_id = _as_str(result.get("rest_id") or item.get("rest_id") or item.get("id_str"))
    core = result.get("core") if isinstance(result.get("core"), dict) else {}
    username = _as_str(
        legacy.get("screen_name")
        or core.get("screen_name")
        or result.get("screen_name")
        or item.get("screen_name")
    )
    display_name = _as_str(
        legacy.get("name")
        or core.get("name")
        or result.get("name")
        or item.get("name")
    )
    if not rest_id or not username:
        return None

    return ParsedAuthor(
        x_user_id=rest_id,
        username=username,
        display_name=display_name,
        description=_as_str(legacy.get("description")),
        verified=_as_bool(legacy.get("verified") or result.get("is_blue_verified")),
        followers_count=_as_int(legacy.get("followers_count")),
        following_count=_as_int(legacy.get("friends_count")),
        post_count=_as_int(legacy.get("statuses_count")),
        profile_image_url=_as_str(legacy.get("profile_image_url_https")),
        raw=result,
    )


def _extract_post(item: dict[str, Any]) -> ParsedPost | None:
    result = _unwrap_result(item)
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = _unwrap_result(result.get("tweet", {}))

    legacy = result.get("legacy") if isinstance(result.get("legacy"), dict) else {}
    if not _looks_like_post(result, legacy):
        return None
    post_id = _as_str(result.get("rest_id") or item.get("rest_id") or legacy.get("id_str"))
    if not post_id:
        return None

    user_result = (
        result.get("core", {}).get("user_results", {}).get("result")
        if isinstance(result.get("core"), dict)
        else None
    )
    user = _extract_user(user_result) if isinstance(user_result, dict) else None
    entities = legacy.get("entities") if isinstance(legacy.get("entities"), dict) else {}
    extended = (
        legacy.get("extended_entities")
        if isinstance(legacy.get("extended_entities"), dict)
        else {}
    )

    return ParsedPost(
        x_post_id=post_id,
        username=user.username if user else None,
        text=_as_str(legacy.get("full_text") or legacy.get("text")),
        created_at=_as_str(legacy.get("created_at")),
        author_user_id=user.x_user_id if user else _as_str(legacy.get("user_id_str")),
        lang=_as_str(legacy.get("lang")),
        conversation_id=_as_str(legacy.get("conversation_id_str")),
        reply_to_post_id=_as_str(legacy.get("in_reply_to_status_id_str")),
        quote_post_id=_as_str(legacy.get("quoted_status_id_str")),
        repost_of_post_id=_nested_post_id(legacy.get("retweeted_status_result")),
        like_count=_as_int(legacy.get("favorite_count")),
        repost_count=_as_int(legacy.get("retweet_count")),
        reply_count=_as_int(legacy.get("reply_count")),
        quote_count=_as_int(legacy.get("quote_count")),
        bookmark_count=_as_int(legacy.get("bookmark_count")),
        view_count=_view_count(result),
        urls=list(entities.get("urls", [])) if isinstance(entities.get("urls"), list) else [],
        hashtags=[
            tag["text"]
            for tag in entities.get("hashtags", [])
            if isinstance(tag, dict) and isinstance(tag.get("text"), str)
        ],
        mentions=[
            mention
            for mention in entities.get("user_mentions", [])
            if isinstance(mention, dict)
        ],
        media=list(extended.get("media", [])) if isinstance(extended.get("media"), list) else [],
        raw=result,
    )


def _unwrap_result(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    result = item.get("result")
    if isinstance(result, dict):
        return _unwrap_result(result)
    return item


def _looks_like_post(result: dict[str, Any], legacy: dict[str, Any]) -> bool:
    typename = _as_str(result.get("__typename"))
    if typename == "User":
        return False
    return (
        typename in {"Tweet", "TweetWithVisibilityResults"}
        or "full_text" in legacy
        or "text" in legacy
        or "id_str" in legacy
        or (
            isinstance(result.get("core"), dict)
            and isinstance(result["core"].get("user_results"), dict)
        )
    )


def _nested_post_id(value: Any) -> str | None:
    result = _unwrap_result(value)
    legacy = result.get("legacy") if isinstance(result.get("legacy"), dict) else {}
    return _as_str(result.get("rest_id") or legacy.get("id_str"))


def _view_count(result: dict[str, Any]) -> int | None:
    views = result.get("views") if isinstance(result.get("views"), dict) else {}
    return _as_int(views.get("count"))


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
