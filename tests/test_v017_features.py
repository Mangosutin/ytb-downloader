from __future__ import annotations


import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch


import pytest


try:
    import yt_dlp  # noqa: F401
except ImportError:
    yt_dlp_stub = types.ModuleType("yt_dlp")
    utils_stub = types.ModuleType("yt_dlp.utils")


    class EntryNotInPlaylist(Exception):
        pass


    utils_stub.EntryNotInPlaylist = EntryNotInPlaylist
    yt_dlp_stub.utils = utils_stub
    yt_dlp_stub.YoutubeDL = Mock
    sys.modules["yt_dlp"] = yt_dlp_stub
    sys.modules["yt_dlp.utils"] = utils_stub


from main import load_linklist
from ytbdl.config import load_config
from ytbdl.core import parse_streamhash
from ytbdl.musicbrainz import lookup_genre


def test_lookup_genre_hit():
    responses = [
        {
            "recordings": [
                {"id": "recording-1"},
            ],
        },
        {
            "id": "recording-1",
            "genres": [{"name": "rock", "count": 10}],
            "releases": [],
            "artist-credit": [],
        },
    ]
    with patch(
        "ytbdl.musicbrainz._request_json",
        side_effect=responses,
    ):
        assert lookup_genre("Song", "Artist") == "rock"


def test_lookup_genre_not_found():
    responses = [
        {"recordings": []},
    ]
    with patch(
        "ytbdl.musicbrainz._request_json",
        side_effect=responses,
    ):
        assert lookup_genre("Unknown", "Unknown") is None


def test_lookup_genre_exception():
    with patch(
        "ytbdl.musicbrainz._request_json",
        side_effect=OSError("network error"),
    ):
        assert lookup_genre("Song", "Artist") is None


def test_parse_streamhash():
    output = (
        "0, SHA256=0123456789abcdef"
        "0123456789abcdef0123456789abcdef0123456789abcdef\n"
    )
    assert parse_streamhash(output) == (
        "0123456789abcdef0123456789abcdef"
        "0123456789abcdef0123456789abcdef"
    )


def test_parse_streamhash_not_found():
    assert parse_streamhash("ffmpeg output without hash") is None


def test_load_linklist_mixed(tmp_path: Path):
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps([
            "https://example.com/a",
            {"url": "https://example.com/b", "mode": "audio"},
            {"url": "https://example.com/c", "mode": "video"},
        ]),
        encoding="utf-8",
    )

    assert load_linklist(path) == [
        {"url": "https://example.com/a", "mode": None},
        {"url": "https://example.com/b", "mode": "audio"},
        {"url": "https://example.com/c", "mode": "video"},
    ]


def test_load_linklist_invalid_root(tmp_path: Path):
    path = tmp_path / "links.json"
    path.write_text('{"url": "https://example.com"}', encoding="utf-8")

    with pytest.raises(ValueError):
        load_linklist(path)


def test_load_linklist_missing_url(tmp_path: Path):
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps([{"mode": "audio"}]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_linklist(path)


def test_main_linklist_processes_all_items(tmp_path: Path):
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps(
            [
                "https://example.com/ok1",
                "https://example.com/skip",
                "https://example.com/fail",
                "https://example.com/ok2",
            ]
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    def fake_download(url: str, mode: str, config: object) -> None:
        calls.append(url)
        if url == "https://example.com/fail":
            raise RuntimeError("download failed")

    archive_results = iter([False, True, False, False])

    with patch(
        "main._archive_contains",
        side_effect=lambda config, video_id: next(archive_results),
    ), patch("main.download", side_effect=fake_download), patch(
        "main.setup_logging"
    ), patch.object(
        sys,
        "argv",
        [
            "ytbdl",
            "--config",
            str(tmp_path / "missing.toml"),
            "--linklist",
            str(path),
        ],
    ):
        from main import main

        assert main() == 1

    assert calls == [
        "https://example.com/ok1",
        "https://example.com/fail",
        "https://example.com/ok2",
    ]


def test_main_linklist_all_success(tmp_path: Path):
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps(["https://example.com/a"]),
        encoding="utf-8",
    )
    with patch("main._archive_contains", return_value=True), patch(
        "main.download"
    ) as download_mock, patch("main.setup_logging"), patch.object(
        sys,
        "argv",
        [
            "ytbdl",
            "--config",
            str(tmp_path / "missing.toml"),
            "--linklist",
            str(path),
        ],
    ):
        from main import main

        assert main() == 0
        download_mock.assert_not_called()


def test_config_v017_defaults_when_file_missing(tmp_path: Path):
    config = load_config(
        tmp_path / "missing.toml",
        app_dir=tmp_path,
    )
    assert config.genre_lookup is True
    assert config.record_audio_hash is True
