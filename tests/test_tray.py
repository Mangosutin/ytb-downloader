from ytbdl.tray import parse_stacked_input


def test_parse_stacked_input_url_only() -> None:
    url, mode = parse_stacked_input("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert mode == ""


def test_parse_stacked_input_mode() -> None:
    url, mode = parse_stacked_input(
        "https://www.youtube.com/watch?v=abc123 --mode audio"
    )
    assert url == "https://www.youtube.com/watch?v=abc123"
    assert mode == "audio"


def test_parse_stacked_input_mode_equals_form() -> None:
    url, mode = parse_stacked_input("https://youtu.be/abc123 --mode=video")
    assert url == "https://youtu.be/abc123"
    assert mode == "video"


def test_parse_stacked_input_invalid_mode_is_ignored() -> None:
    url, mode = parse_stacked_input(
        "https://www.youtube.com/watch?v=abc --mode xyz"
    )
    assert url == "https://www.youtube.com/watch?v=abc"
    assert mode == ""


def test_parse_stacked_input_no_value_mode_is_ignored() -> None:
    url, mode = parse_stacked_input("https://www.youtube.com/watch?v=abc --mode")
    assert url == "https://www.youtube.com/watch?v=abc"
    assert mode == ""


def test_parse_stacked_input_no_url_returns_empty() -> None:
    assert parse_stacked_input("") == ("", "")
    assert parse_stacked_input("--mode audio") == ("", "")
