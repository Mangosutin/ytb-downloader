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
    force_ipv4: bool
    subtitles: bool
    thumbnails: bool
    embed_metadata: bool
    cookies: Path | None
    embed_album_art: bool = True
    audio_bitrate: int = 256
    audio_bit_depth: int | None = None
    audio_sample_rate: int | None = None
    genre_lookup: bool = True
    record_audio_hash: bool = True


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
        try:
            with config_path.open("rb") as file:
                data = tomllib.load(file)
        except tomllib.TOMLDecodeError as exc:
            message = str(exc)
            if r"Unescaped '\' in a string" in message:
                message += (
                    "\nWindowsのパスは、"
                    "ffmpeg_location = 'E:\\ffmpeg' のように"
                    "シングルクォートで囲んでください。"
                )
            raise ValueError(
                f"設定ファイルのTOML形式が不正です:{config_path}\n{message}"
            ) from exc
    else:
        logger.info(
            "設定ファイルが見つかりません。既定値を使用します: %s",
            config_path,
        )
        data = {}
    base_dir = config_path.parent
    download_dir = _resolve_path(data.get("download_dir", "downloads"), base_dir)
    archive_file = _resolve_path(data.get("archive_file", "archive.txt"), base_dir)
    log_dir = _resolve_path(data.get("log_dir", "logs"), base_dir)
    default_mode = str(data.get("default_mode", "video"))
    if default_mode not in {"video", "audio"}:
        raise ValueError("default_mode は video または audio にしてください。")
    audio_format = str(data.get("audio_format", "mp3"))
    if audio_format not in {"mp3", "original"}:
        raise ValueError("audio_format は mp3 または original にしてください。")
    ffmpeg_location = _resolve_path(data.get("ffmpeg_location", "ffmpeg"), app_dir)
    embed_album_art = _get_bool(data, "embed_album_art", True)
    audio_bitrate = data.get("audio_bitrate", 256)
    if (
        isinstance(audio_bitrate, bool)
        or not isinstance(audio_bitrate, int)
        or audio_bitrate <= 0
    ):
        raise ValueError("audio_bitrate は正の整数で指定してください。")
    audio_bit_depth = data.get("audio_bit_depth")
    if audio_bit_depth is not None and (
        isinstance(audio_bit_depth, bool)
        or not isinstance(audio_bit_depth, int)
        or audio_bit_depth not in (16, 24, 32)
    ):
        raise ValueError(
            "audio_bit_depth は 16、24、32 のいずれかで指定してください。"
        )
    audio_sample_rate = data.get("audio_sample_rate")
    if audio_sample_rate is not None and (
        isinstance(audio_sample_rate, bool)
        or not isinstance(audio_sample_rate, int)
        or audio_sample_rate <= 0
    ):
        raise ValueError("audio_sample_rate は正の整数で指定してください。")
    cookies_value = data.get("cookies", "")
    cookies = (
        _resolve_path(cookies_value, base_dir) if cookies_value else None
    )
    return Config(
        download_dir=download_dir,
        archive_file=archive_file,
        log_dir=log_dir,
        default_mode=default_mode,
        audio_format=audio_format,
        ffmpeg_location=ffmpeg_location,
        force_ipv4=_get_bool(data, "force_ipv4", True),
        subtitles=_get_bool(data, "subtitles", False),
        thumbnails=_get_bool(data, "thumbnails", False),
        embed_metadata=_get_bool(data, "embed_metadata", False),
        cookies=cookies,
        embed_album_art=embed_album_art,
        audio_bitrate=audio_bitrate,
        audio_bit_depth=audio_bit_depth,
        audio_sample_rate=audio_sample_rate,
        genre_lookup=_get_bool(data, "genre_lookup", True),
        record_audio_hash=_get_bool(data, "record_audio_hash", True),
    )
