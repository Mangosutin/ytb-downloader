from ytbdl.clipboard import find_youtube_url


def test_find_youtube_url_returns_none_without_url() -> None:
    assert find_youtube_url("hello world") is None
    assert find_youtube_url("") is None
    assert find_youtube_url(None) is None


def test_find_youtube_url_extracts_watch_url() -> None:
    text = "Copy this: https://www.youtube.com/watch?v=dQw4w9WgXcQ to see."
    assert find_youtube_url(text) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_find_youtube_url_extracts_youtu_be_url() -> None:
    text = "see https://youtu.be/dQw4w9WgXcQ thanks"
    assert find_youtube_url(text) == "https://youtu.be/dQw4w9WgXcQ"


def test_find_youtube_url_extracts_music_watch_url() -> None:
    text = "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
    assert find_youtube_url(text) == text


def test_find_youtube_url_strips_trailing_punctuation() -> None:
    text = "check https://youtu.be/abc123."
    assert find_youtube_url(text) == "https://youtu.be/abc123"


def test_find_youtube_url_returns_first_match() -> None:
    text = "https://www.youtube.com/watch?v=A then https://www.youtube.com/watch?v=B"
    assert find_youtube_url(text) == "https://www.youtube.com/watch?v=A"
