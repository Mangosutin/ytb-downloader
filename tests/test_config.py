from pathlib import Path

import pytest

from ytbdl.config import load_config


def test_load_config_accepts_windows_literal_path(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "ffmpeg_location = 'E:\\app\\ffmpeg'\n",
        encoding="utf-8",
    )

    config = load_config(config_file, app_dir=tmp_path)

    assert isinstance(config.ffmpeg_location, Path)


def test_load_config_explains_unescaped_windows_path(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'ffmpeg_location = "E:\\app\\ffmpeg"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="シングルクォート"):
        load_config(config_file, app_dir=tmp_path)
