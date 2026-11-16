from ytbdl.cli import resolve_url


def test_command_line_url_has_priority() -> None:
    assert resolve_url("https://example.test/watch?v=1", {
        "YTB_DOWNLOADER_URL": "https://example.test/playlist?list=abc"
    }) == "https://example.test/watch?v=1"


def test_launcher_environment_url_is_used() -> None:
    url = "https://www.youtube.com/watch?v=1jdTOxzXskE&list=PLM1t88YmeLxs&pp=x"
    assert resolve_url(None, {"YTB_DOWNLOADER_URL": url}) == url


def test_missing_url_returns_none() -> None:
    assert resolve_url(None, {}) is None
