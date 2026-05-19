from xoctopus.config import parse_config
from xoctopus.source_config import (
    add_source,
    delete_source,
    make_source,
    set_browser_headless,
    set_source_enabled,
)


def test_parse_config_minimal_source():
    config = parse_config(
        {
            "sources": [
                {
                    "name": "openai",
                    "type": "user_timeline",
                    "value": "OpenAI",
                }
            ]
        }
    )

    assert config.app.db_path.as_posix() == "data/xoctopus.sqlite3"
    assert config.browser.headless is False
    assert config.browser.channel == ""
    assert config.browser.executable_path == ""
    assert len(config.sources) == 1
    assert config.sources[0].poll_interval_seconds == 1800


def test_parse_config_browser_system_browser_options():
    config = parse_config(
        {
            "browser": {
                "channel": "chrome",
                "executable_path": "/usr/bin/google-chrome",
            },
            "sources": [
                {
                    "name": "openai",
                    "type": "user_timeline",
                    "value": "OpenAI",
                }
            ],
        }
    )

    assert config.browser.channel == "chrome"
    assert config.browser.executable_path == "/usr/bin/google-chrome"


def test_source_config_add_disable_delete_round_trip(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[app]
db_path = "data/xoctopus.sqlite3"

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

    add_source(
        config_path,
        make_source(value="OpenAIDevs", poll_interval_seconds=3600),
    )
    set_source_enabled(config_path, "openaidevs_timeline", False)
    config = parse_config_from_path(config_path)

    assert [source.name for source in config.sources] == [
        "openai_timeline",
        "openaidevs_timeline",
    ]
    assert config.sources[1].enabled is False
    assert config.sources[1].poll_interval_seconds == 3600

    delete_source(config_path, "openaidevs_timeline")
    config = parse_config_from_path(config_path)

    assert [source.name for source in config.sources] == ["openai_timeline"]


def test_set_browser_headless_round_trip(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[browser]
headless = false

[[sources]]
name = "openai_timeline"
type = "user_timeline"
value = "OpenAI"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    set_browser_headless(config_path, True)
    config = parse_config_from_path(config_path)

    assert config.browser.headless is True


def parse_config_from_path(path):
    import tomllib

    with path.open("rb") as fh:
        return parse_config(tomllib.load(fh))
