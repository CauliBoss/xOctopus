from xoctopus.parser.x_timeline import parse_timeline_response


def test_parse_timeline_response_scaffold_is_empty():
    result = parse_timeline_response({})

    assert result.authors == []
    assert result.posts == []


def test_parse_timeline_response_extracts_common_graphql_shape():
    payload = {
        "data": {
            "threaded_conversation_with_injections_v2": {
                "instructions": [
                    {
                        "entries": [
                            {
                                "content": {
                                    "itemContent": {
                                        "tweet_results": {
                                            "result": {
                                                "__typename": "Tweet",
                                                "rest_id": "123",
                                                "core": {
                                                    "user_results": {
                                                        "result": {
                                                                "rest_id": "42",
                                                                "core": {
                                                                    "screen_name": "OpenAI",
                                                                    "name": "OpenAI",
                                                                },
                                                                "legacy": {
                                                                    "followers_count": 10,
                                                                },
                                                        }
                                                    }
                                                },
                                                "legacy": {
                                                    "full_text": "hello world",
                                                    "created_at": "Mon May 18 00:00:00 +0000 2026",
                                                    "favorite_count": 7,
                                                    "retweet_count": 3,
                                                    "reply_count": 2,
                                                    "quote_count": 1,
                                                    "lang": "en",
                                                    "entities": {
                                                        "hashtags": [{"text": "AI"}],
                                                        "urls": [{"expanded_url": "https://example.com"}],
                                                    },
                                                },
                                                "views": {"count": "99"},
                                            }
                                        }
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        }
    }

    result = parse_timeline_response(payload)

    assert len(result.authors) == 1
    assert result.authors[0].username == "OpenAI"
    assert len(result.posts) == 1
    assert result.posts[0].x_post_id == "123"
    assert result.posts[0].username == "OpenAI"
    assert result.posts[0].text == "hello world"
    assert result.posts[0].like_count == 7
    assert result.posts[0].view_count == 99
