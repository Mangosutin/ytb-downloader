from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    download_dir: Path
    archive_file: Path
    log_dir: Path
    default_mode: str
    audio_format: str
    ffmpeg_location: Path
    subtitles: bool
    thumbnails: bool
    embed_metadata: bool
    cookies: Path | None


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _get_bool(
    data: dict[str, Any],
    key: str,
    default: bool,
) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key}は true または false で指定してください。")
    return value


def load_config(
    config_path: Path,
    app_dir: Path | None = None,
) -> Config:
    config_path = config_path.expanduser().resolve()
    app_dir = (app_dir or Path(__file__).resolve().parent.parent).resolve()
    if config_path.exists():
        with config_path.open("rb") as file:
            data = tomllib.load(file)
        if not isinstance(data, dict):
            raise ValueError("設定ファイルの形式が不正です。")
        base_dir = config_path.parent
        logger.info("設定ファイルを読み込みました: %s", config_path)
    else:
        data = {}
        base_dir = app_dir
        logger.info("設定ファイルがないため既定値を使用します。")

    default_mode = data.get("default_mode", "video")
    if default_mode not in ("video", "audio"):
        raise ValueError("default_mode は video または audio にしてください。")
    audio_format = data.get("audio_format", "mp3")
    if audio_format not in ("mp3", "original"):
        raise ValueError("audio_format は mp3 または original にしてください。")
    download_dir = _resolve_path(
        data.get("download_dir", "downloads"),
        base_dir,
    )
    archive_file = _resolve_path(
        data.get("archive_file", "archive.txt"),
        base_dir,
    )
    log_dir = _resolve_path(
        data.get("log_dir", "logs"),
        base_dir,
    )
    ffmpeg_location = _resolve_path(
        data.get("ffmpeg_location", "ffmpeg"),
        base_dir,
    )
    cookies_value = data.get("cookies")
    cookies = (
        _resolve_path(cookies_value, base_dir)
        if cookies_value
        else None
    )

    return Config(
        download_dir=download_dir,
        archive_file=archive_file,
        log_dir=log_dir,
        default_mode=default_mode,
        audio_format=audio_format,
        ffmpeg_location=ffmpeg_location,
        subtitles=_get_bool(data, "subtitles", False),
        thumbnails=_get_bool(data, "thumbnails", False),
        embed_metadata=_get_bool(data, "embed_metadata", False),
        cookies=cookies,
    )
