from __future__ import annotations

import logging
from typing import Any

import yt_dlp

from ytbdl.config import Config
from ytbdl.naming import (
    build_audio_name,
    sanitize_filename,
)

logger = logging.getLogger(__name__)


class YTDLPLogger:
    def debug(self, message: str) -> None:
        if message.startswith("[debug] "):
            logger.debug(message)
        else:
            logger.info(message)

    def info(self, message: str) -> None:
        logger.info(message)

    def warning(self, message: str) -> None:
        logger.warning(message)

    def error(self, message: str) -> None:
        logger.error(message)


def _progress_hook(data: dict[str, Any]) -> None:
    status = data.get("status")
    if status == "downloading":
        downloaded = data.get("downloaded_bytes", 0)
        total = (
            data.get("total_bytes")
            or data.get("total_bytes_estimate")
        )
        if total:
            logger.info(
                "ダウンロード中: %.1f%%",
                downloaded / total * 100,
            )
    elif status == "finished":
        logger.info(
            "ダウンロード完了: %s",
            data.get("filename", ""),
        )


def _get_ffmpeg_location(config: Config) -> str | None:
    path = config.ffmpeg_location
    if not path.exists():
        logger.warning(
            "ffmpegの配置先が存在しません: %s",
            path,
        )
        return None
    return str(path)


def _prepare_entry(
    entry: dict[str, Any],
    mode: str,
    config: Config,
) -> None:
    if mode != "audio":
        return
    naming = build_audio_name(entry)
    entry["title"] = naming["filename"]
    if config.embed_metadata:
        entry["track"] = naming["track"]
        if naming["artist"]:
            entry["artist"] = naming["artist"]
        if naming["cover"] and naming["album_artist"]:
            entry["album_artist"] = naming["album_artist"]


def _prepare_entries(
    info: dict[str, Any],
    mode: str,
    config: Config,
) -> None:
    entries = info.get("entries")
    if entries:
        for entry in entries:
            if isinstance(entry, dict):
                _prepare_entry(entry, mode, config)
    else:
        _prepare_entry(info, mode, config)


def _build_output_template(
    info: dict[str, Any],
    mode: str,
    config: Config,
) -> str:
    is_playlist = (
        info.get("_type") in ("playlist", "multi_video")
        or bool(info.get("entries"))
    )
    if is_playlist:
        playlist_title = sanitize_filename(
            str(info.get("title") or "playlist")
        )
        output_dir = config.download_dir / playlist_title
    else:
        output_dir = config.download_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    if mode == "video":
        filename = "%(title)s [%(id)s].%(ext)s"
    else:
        filename = "%(title)s.%(ext)s"
    return str(output_dir / filename)


def _build_options(
    config: Config,
    mode: str,
    output_template: str,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "outtmpl": {
            "default": output_template,
        },
        "download_archive": str(config.archive_file),
        "noplaylist": False,
        "logger": YTDLPLogger(),
        "progress_hooks": [_progress_hook],
        "ignoreerrors": False,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "quiet": True,
        "no_warnings": False,
        "writesubtitles": config.subtitles,
        "allsubtitles": config.subtitles,
        "writethumbnail": config.thumbnails,
    }
    ffmpeg_location = _get_ffmpeg_location(config)
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    if mode == "video":
        options.update({
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
        })
    elif mode == "audio":
        options["format"] = "bestaudio/best"
        if config.audio_format == "mp3":
            options["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }]
        if config.embed_metadata:
            options.setdefault("postprocessors", []).append({
                "key": "FFmpegMetadata",
                "add_metadata": True,
            })

    return options


def download(
    url: str,
    mode: str,
    config: Config,
) -> None:
    if mode not in ("video", "audio"):
        raise ValueError(f"不正なモードです:{mode}")
    if not url or not url.strip():
        raise ValueError("URLが指定されていません。")
    config.download_dir.mkdir(parents=True, exist_ok=True)
    config.archive_file.parent.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logger.info("ダウンロードを開始します。")
    logger.info("URL: %s", url)
    logger.info("モード: %s", mode)
    if mode == "audio":
        logger.info("音声形式: %s", config.audio_format)
    try:
        with yt_dlp.YoutubeDL({
            "quiet": True,
            "no_warnings": False,
            "logger": YTDLPLogger(),
        }) as metadata_ydl:
            info = metadata_ydl.extract_info(
                url,
                download=False,
            )
            if not info:
                raise RuntimeError(
                    "動画情報を取得できませんでした。"
                )
            if info.get("_type") == "channel":
                raise ValueError(
                    "チャンネル全動画の一括ダウンロードには対応していません。"
                )
            _prepare_entries(info, mode, config)
            output_template = _build_output_template(
                info,
                mode,
                config,
            )
            options = _build_options(
                config,
                mode,
                output_template,
            )
            with yt_dlp.YoutubeDL(options) as ydl:
                result = ydl.process_ie_result(
                    info,
                    download=True,
                )

                if result is None:
                    logger.warning(
                        "ダウンロード対象がありませんでした。"
                    )
                else:
                    logger.info("ダウンロード処理が完了しました。")
    except Exception:
        logger.exception("ダウンロードに失敗しました。")
        raise
