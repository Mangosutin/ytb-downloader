from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ytbdl.config import Config, load_config
from ytbdl.core import _build_options


def _write_config(tmp_path: Path, body: str) -> Path:
    config_file = tmp_path / "config.toml"
    config_file.write_text(body, encoding="utf-8")
    return config_file


def _load(tmp_path: Path, body: str) -> Config:
    return load_config(_write_config(tmp_path, body), app_dir=tmp_path)


def _options(config: Config, tmp_path: Path) -> dict:
    return _build_options(
        config,
        "audio",
        str(tmp_path / "out" / "%(title)s.%(ext)s"),
    )


def test_missing_config_uses_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "config.toml", app_dir=tmp_path)

    assert config.embed_album_art is True
    assert config.audio_bitrate == 256
    assert config.audio_bit_depth is None
    assert config.audio_sample_rate is None
    assert config.cookies is None


def test_audio_defaults(tmp_path: Path) -> None:
    config = _load(tmp_path, 'default_mode = "audio"\n')

    assert config.embed_album_art is True
    assert config.audio_bitrate == 256
    assert config.audio_bit_depth is None
    assert config.audio_sample_rate is None


def test_audio_settings_are_loaded(tmp_path: Path) -> None:
    config = _load(
        tmp_path,
        "embed_album_art = false\n"
        "audio_bitrate = 192\n"
        "audio_bit_depth = 16\n"
        "audio_sample_rate = 44100\n",
    )

    assert config.embed_album_art is False
    assert config.audio_bitrate == 192
    assert config.audio_bit_depth == 16
    assert config.audio_sample_rate == 44100


def test_invalid_audio_bit_depth_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _load(tmp_path, "audio_bit_depth = 20\n")


def test_invalid_audio_sample_rate_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _load(tmp_path, "audio_sample_rate = 0\n")


def test_invalid_audio_bitrate_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _load(tmp_path, "audio_bitrate = 0\n")


def test_config_is_frozen(tmp_path: Path) -> None:
    config = _load(tmp_path, 'default_mode = "audio"\n')

    with pytest.raises(FrozenInstanceError):
        config.audio_bitrate = 128


def test_embed_album_art_option(tmp_path: Path) -> None:
    config = _load(tmp_path, "embed_album_art = true\n")
    options = _options(config, tmp_path)
    assert {"key": "EmbedThumbnail"} in options.get("postprocessors", [])
    assert options["writethumbnail"] is True

    config = _load(tmp_path, "embed_album_art = false\n")
    options = _options(config, tmp_path)
    assert {"key": "EmbedThumbnail"} not in options.get("postprocessors", [])
    assert options["writethumbnail"] is False


def test_audio_bitrate_option(tmp_path: Path) -> None:
    config = _load(tmp_path, "")
    options = _options(config, tmp_path)
    assert {
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "256",
    } in options.get("postprocessors", [])

    config = _load(tmp_path, "audio_bitrate = 192\n")
    options = _options(config, tmp_path)
    assert {
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    } in options.get("postprocessors", [])


def test_audio_quality_args_option(tmp_path: Path) -> None:
    config = _load(
        tmp_path,
        "audio_bit_depth = 16\n" "audio_sample_rate = 44100\n",
    )
    options = _options(config, tmp_path)
    assert options["postprocessor_args"] == {
        "FFmpegExtractAudio": ["-ar", "44100", "-sample_fmt", "s16p"],
    }

    config = _load(tmp_path, "")
    options = _options(config, tmp_path)
    assert "postprocessor_args" not in options


def test_audio_quality_args_not_applied_for_original(tmp_path: Path) -> None:
    config = _load(
        tmp_path,
        'audio_format = "original"\n'
        "audio_bit_depth = 24\n"
        "audio_sample_rate = 48000\n",
    )
    options = _options(config, tmp_path)
    assert "postprocessor_args" not in options
