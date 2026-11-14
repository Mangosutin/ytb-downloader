from ytbdl.naming import (
    build_audio_filename,
    build_audio_name,
    build_video_name,
    extract_feat,
    extract_remixes,
    is_cover,
    normalize_feat,
    sanitize_filename,
)


def test_normalize_feat():
    assert normalize_feat("曲 feat. A") == "曲 feat. A"
    assert normalize_feat("曲 ft. A") == "曲 feat. A"
    assert normalize_feat("曲 featuring A") == "曲 feat. A"


def test_extract_feat():
    track, feat = extract_feat("夜に駆ける feat. A")

    assert track == "夜に駆ける"
    assert feat == "(feat. A)"


def test_extract_feat_multiple_artists():
    track, feat = extract_feat(
        "夜に駆ける feat. A & B"
    )

    assert track == "夜に駆ける"
    assert feat == "(feat. A & B)"


def test_extract_remix():
    track, remixes = extract_remixes(
        "夜に駆ける (DJ Remix)"
    )

    assert track == "夜に駆ける"
    assert remixes == ["(DJ Remix)"]


def test_extract_multiple_remixes():
    track, remixes = extract_remixes(
        "夜に駆ける (DJ Remix) (Extended Remix)"
    )

    assert track == "夜に駆ける"
    assert remixes == [
        "(DJ Remix)",
        "(Extended Remix)",
    ]


def test_audio_filename():
    info = {
        "title": "YOASOBI - 夜に駆ける (Official Music Video)",
        "uploader": "Uploader",
        "id": "123456",
    }

    result = build_audio_filename(info)

    assert result == "夜に駆ける - YOASOBI"


def test_audio_filename_with_feat():
    info = {
        "title": "Artist - Song feat. Guest",
        "uploader": "Uploader",
        "id": "123456",
    }

    result = build_audio_filename(info)

    assert result == "Song (feat. Guest) - Artist"


def test_audio_filename_with_remix():
    info = {
        "title": "Artist - Song (DJ Remix)",
        "uploader": "Uploader",
        "id": "123456",
    }

    result = build_audio_filename(info)

    assert result == "Song (DJ Remix) - Artist"


def test_audio_filename_with_feat_and_remix():
    info = {
        "title": "Artist - Song feat. Guest (DJ Remix)",
        "uploader": "Uploader",
        "id": "123456",
    }

    result = build_audio_filename(info)

    assert result == "Song (feat. Guest) (DJ Remix) - Artist"


def test_audio_fallback():
    info = {
        "title": "Unrecognized title",
        "uploader": "",
        "id": "123456",
    }

    result = build_audio_filename(info)

    assert result == "Unrecognized title"


def test_video_filename():
    info = {
        "title": "Sample Video",
        "id": "abc123",
    }

    assert build_video_name(info) == "Sample Video [abc123]"


def test_sanitize_filename():
    assert sanitize_filename('test<>:"/\\|?*name') == (
        "test_________name"
    )


def test_sanitize_reserved_filename():
    assert sanitize_filename("CON") == "_CON"


def test_build_audio_name_metadata():
    info = {
        "title": "Song",
        "track": "Song",
        "artist": "Artist",
        "uploader": "Uploader",
    }

    result = build_audio_name(info)

    assert result["filename"] == "Song - Artist"
    assert result["track"] == "Song"
    assert result["artist"] == "Artist"
    assert result["cover"] is False


def test_cover_detection():
    assert is_cover("夜に駆ける Cover")
    assert is_cover("夜に駆ける カバー")
    assert is_cover("【歌ってみた】夜に駆ける")
    assert not is_cover("夜に駆ける Official Music Video")


def test_cover_filename():
    info = {
        "title": "【歌ってみた】夜に駆ける / covered by A",
        "uploader": "Uploader",
        "id": "123456",
    }

    result = build_audio_filename(info)

    assert result == "夜に駆ける (Cover) - A"


def test_cover_artist_fallback_to_uploader():
    info = {
        "title": "【歌ってみた】夜に駆ける",
        "uploader": "Uploader",
        "id": "123456",
    }

    result = build_audio_filename(info)

    assert result == "夜に駆ける (Cover) - Uploader"


def test_audio_filename_with_metadata():
    info = {
        "title": "Official Music Video",
        "track": "夜に駆ける",
        "artist": "YOASOBI",
        "uploader": "YOASOBI",
        "id": "123456",
    }

    result = build_audio_filename(info)

    assert result == "夜に駆ける - YOASOBI"
