from __future__ import annotations

from pathlib import Path

import pytest
import yt_dlp
from yt_dlp.utils import EntryNotInPlaylist

from ytbdl.config import Config
from ytbdl.core import _build_options, download


def _config(tmp_path: Path, **overrides) -> Config:
    values = {
        "download_dir": tmp_path / "downloads",
        "archive_file": tmp_path / "archive.txt",
        "log_dir": tmp_path / "logs",
        "default_mode": "video",
        "audio_format": "mp3",
        "ffmpeg_location": tmp_path / "ffmpeg",
        "force_ipv4": True,
        "subtitles": False,
        "thumbnails": False,
        "embed_metadata": False,
        "cookies": None,
        "embed_album_art": True,
        "audio_bitrate": 256,
        "audio_bit_depth": None,
        "audio_sample_rate": None,
    }
    values.update(overrides)
    return Config(**values)


def _entry(video_id: str, title: str, artist: str) -> dict:
    return {
        "id": video_id,
        "title": title,
        "uploader": artist,
        "track": title,
        "artist": artist,
    }


def _playlist_info(title: str, entries: list) -> dict:
    return {
        "_type": "playlist",
        "title": title,
        "entries": entries,
    }


class FakeYoutubeDL:
    """YoutubeDL のモック。生成された全インスタンスを記録する。"""

    instances: list["FakeYoutubeDL"] = []
    extract_info_results: list = []
    extract_urls: list[str] = []
    process_infos: list = []
    processed_entry_ids: list[str] = []
    process_result: object = {}
    process_error: Exception | None = None

    def __init__(self, options) -> None:
        self.options = options
        self.params = options
        type(self).instances.append(self)

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def extract_info(self, url, download=False):
        type(self).extract_urls.append(url)
        if type(self).extract_info_results:
            return type(self).extract_info_results.pop(0)
        return None

    def process_ie_result(self, info, download=True):
        type(self).process_infos.append(info)
        # Process all entries, ignoring playlist_items (like real yt-dlp).
        for entry in info.get("entries") or []:
            if isinstance(entry, dict) and entry.get("id"):
                type(self).processed_entry_ids.append(entry["id"])
        if type(self).process_error is not None:
            raise type(self).process_error
        return type(self).process_result


@pytest.fixture(autouse=True)
def _reset_fake(monkeypatch):
    FakeYoutubeDL.instances = []
    FakeYoutubeDL.extract_info_results = []
    FakeYoutubeDL.extract_urls = []
    FakeYoutubeDL.process_infos = []
    FakeYoutubeDL.processed_entry_ids = []
    FakeYoutubeDL.process_result = {}
    FakeYoutubeDL.process_error = None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    yield


def test_all_archived_playlist_finishes_normally(tmp_path: Path) -> None:
    config = _config(tmp_path)
    FakeYoutubeDL.extract_info_results = [
        _playlist_info("テストプレイリスト", []),
    ]

    download(
        "https://www.youtube.com/watch?v=1jdTOxzXskE&list=PLM1t88YmeLxs",
        "audio",
        config,
    )

    # ダウンロード用のインスタンスは作られず、例外も発生しない。
    assert len(FakeYoutubeDL.instances) == 1
    assert "download_archive" not in FakeYoutubeDL.instances[0].options


def test_playlist_title_is_not_renamed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    entries = [
        _entry("aaa111", "テスト曲1", "テスト歌手1"),
        _entry("bbb222", "テスト曲2", "テスト歌手2"),
    ]
    info = _playlist_info("テストプレイリスト", entries)
    FakeYoutubeDL.extract_info_results = [info]

    download(
        "https://www.youtube.com/playlist?list=PLM1t88YmeLxs",
        "audio",
        config,
    )

    # プレイリスト本体のタイトルには命名を適用しない。
    assert info["title"] == "テストプレイリスト"
    # 各エントリには命名が適用される。
    assert entries[0]["title"] == "テスト曲1 - テスト歌手1"
    assert entries[1]["title"] == "テスト曲2 - テスト歌手2"
    assert len(FakeYoutubeDL.instances) == 2


def test_single_archived_video_finishes_normally(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.archive_file.write_text(
        "youtube 1jdTOxzXskE\n",
        encoding="utf-8",
    )
    FakeYoutubeDL.extract_info_results = [None]

    download(
        "https://www.youtube.com/watch?v=1jdTOxzXskE",
        "audio",
        config,
    )

    assert len(FakeYoutubeDL.instances) == 1


def test_entry_not_in_playlist_finishes_normally(tmp_path: Path) -> None:
    config = _config(tmp_path)
    info = _playlist_info(
        "テストプレイリスト",
        [_entry("aaa111", "テスト曲1", "テスト歌手1")],
    )
    FakeYoutubeDL.extract_info_results = [info]
    FakeYoutubeDL.process_error = EntryNotInPlaylist("Entry 1 cannot be found")

    download(
        "https://www.youtube.com/watch?v=aaa111&list=PLM1t88YmeLxs",
        "audio",
        config,
    )

    assert len(FakeYoutubeDL.instances) == 2


def test_extraction_has_no_download_archive(tmp_path: Path) -> None:
    config = _config(tmp_path)
    info = _playlist_info(
        "テストプレイリスト",
        [_entry("aaa111", "テスト曲1", "テスト歌手1")],
    )
    FakeYoutubeDL.extract_info_results = [info]

    download(
        "https://www.youtube.com/playlist?list=PLM1t88YmeLxs",
        "audio",
        config,
    )

    assert len(FakeYoutubeDL.instances) == 2
    assert "download_archive" not in FakeYoutubeDL.instances[0].options
    assert (
        FakeYoutubeDL.instances[1].options["download_archive"]
        == str(config.archive_file)
    )


def test_index_url_downloads_only_selected_item(tmp_path: Path) -> None:
    config = _config(tmp_path)
    entries = [
        _entry("aaa111", "テスト曲1", "テスト歌手1"),
        _entry("bbb222", "テスト曲2", "テスト歌手2"),
    ]
    info = _playlist_info("テストプレイリスト", entries)
    FakeYoutubeDL.extract_info_results = [info]

    download(
        "https://www.youtube.com/watch?v=bbb222&list=PLM1t88YmeLxs&index=2",
        "audio",
        config,
    )

    assert len(FakeYoutubeDL.instances) == 2
    assert FakeYoutubeDL.instances[0].options["playlist_items"] == "2"
    assert FakeYoutubeDL.instances[1].options["playlist_items"] == "2"
    assert FakeYoutubeDL.process_infos[0]["entries"] == [entries[1]]
    assert FakeYoutubeDL.processed_entry_ids == ["bbb222"]


def test_url_without_index_downloads_whole_playlist(tmp_path: Path) -> None:
    config = _config(tmp_path)
    info = _playlist_info(
        "テストプレイリスト",
        [_entry("aaa111", "テスト曲1", "テスト歌手1")],
    )
    FakeYoutubeDL.extract_info_results = [info]

    download(
        "https://www.youtube.com/watch?v=aaa111&list=PLM1t88YmeLxs",
        "audio",
        config,
    )

    assert len(FakeYoutubeDL.instances) == 2
    assert "playlist_items" not in FakeYoutubeDL.instances[1].options


def test_playlist_url_ignores_index(tmp_path: Path) -> None:
    config = _config(tmp_path)
    info = _playlist_info(
        "テストプレイリスト",
        [_entry("aaa111", "テスト曲1", "テスト歌手1")],
    )
    FakeYoutubeDL.extract_info_results = [info]

    download(
        "https://www.youtube.com/playlist?list=PLM1t88YmeLxs&index=2",
        "audio",
        config,
    )

    assert "playlist_items" not in FakeYoutubeDL.instances[1].options


def test_invalid_index_falls_back_to_single_video(tmp_path: Path) -> None:
    config = _config(tmp_path)
    info = {
        "id": "aaa111",
        "title": "テスト曲1",
        "uploader": "テスト歌手1",
        "track": "テスト曲1",
        "artist": "テスト歌手1",
    }
    FakeYoutubeDL.extract_info_results = [info]

    download(
        "https://www.youtube.com/watch?v=aaa111&list=PLM1t88YmeLxs&index=abc",
        "audio",
        config,
    )

    assert FakeYoutubeDL.extract_urls == [
        "https://www.youtube.com/watch?v=aaa111",
    ]
    assert "playlist_items" not in FakeYoutubeDL.instances[1].options


def test_out_of_range_index_falls_back_to_single_video(tmp_path: Path) -> None:
    config = _config(tmp_path)
    entries = [
        _entry("aaa111", "テスト曲1", "テスト歌手1"),
        _entry("bbb222", "テスト曲2", "テスト歌手2"),
    ]
    playlist = _playlist_info("テストプレイリスト", entries)
    playlist["playlist_count"] = 2
    single = {
        "id": "aaa111",
        "title": "テスト曲1",
        "uploader": "テスト歌手1",
        "track": "テスト曲1",
        "artist": "テスト歌手1",
    }
    FakeYoutubeDL.extract_info_results = [playlist, single]

    download(
        "https://www.youtube.com/watch?v=aaa111&list=PLM1t88YmeLxs&index=10",
        "audio",
        config,
    )

    assert FakeYoutubeDL.extract_urls == [
        "https://www.youtube.com/watch?v=aaa111&list=PLM1t88YmeLxs&index=10",
        "https://www.youtube.com/watch?v=aaa111",
    ]
    assert "playlist_items" not in FakeYoutubeDL.instances[1].options


def test_embed_album_art_option(tmp_path: Path) -> None:
    config = _config(tmp_path, embed_album_art=True)
    options = _build_options(
        config,
        "audio",
        str(tmp_path / "out" / "%(title)s.%(ext)s"),
    )
    postprocessors = options.get("postprocessors", [])
    assert {"key": "EmbedThumbnail"} in postprocessors
    assert options["writethumbnail"] is True

    config = _config(tmp_path, embed_album_art=False)
    options = _build_options(
        config,
        "audio",
        str(tmp_path / "out" / "%(title)s.%(ext)s"),
    )
    postprocessors = options.get("postprocessors", [])
    assert {"key": "EmbedThumbnail"} not in postprocessors
    assert options["writethumbnail"] is False


def test_audio_bitrate_option(tmp_path: Path) -> None:
    config = _config(tmp_path)
    options = _build_options(
        config,
        "audio",
        str(tmp_path / "out" / "%(title)s.%(ext)s"),
    )
    postprocessors = options.get("postprocessors", [])
    assert {
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "256",
    } in postprocessors

    config = _config(tmp_path, audio_bitrate=192)
    options = _build_options(
        config,
        "audio",
        str(tmp_path / "out" / "%(title)s.%(ext)s"),
    )
    postprocessors = options.get("postprocessors", [])
    assert {
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    } in postprocessors


def test_audio_quality_args_option(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        audio_bit_depth=16,
        audio_sample_rate=44100,
    )
    options = _build_options(
        config,
        "audio",
        str(tmp_path / "out" / "%(title)s.%(ext)s"),
    )
    assert options["postprocessor_args"] == {
        "FFmpegExtractAudio": ["-ar", "44100", "-sample_fmt", "s16p"],
    }

    config = _config(tmp_path)
    options = _build_options(
        config,
        "audio",
        str(tmp_path / "out" / "%(title)s.%(ext)s"),
    )
    assert "postprocessor_args" not in options


def test_audio_quality_args_not_applied_for_original(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        audio_format="original",
        audio_bit_depth=24,
        audio_sample_rate=48000,
    )
    options = _build_options(
        config,
        "audio",
        str(tmp_path / "out" / "%(title)s.%(ext)s"),
    )
    assert "postprocessor_args" not in options
