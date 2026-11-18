from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import yt_dlp
from yt_dlp.utils import EntryNotInPlaylist

from ytbdl.config import Config
from ytbdl.musicbrainz import lookup_genre
from ytbdl.naming import (
    build_audio_name,
    sanitize_filename,
)

logger = logging.getLogger(__name__)

# ffmpeg の -sample_fmt に渡すサンプル形式。24 bit は
# ffmpeg の PCM 変換で 32 bit 扱いになるため s32p を使う。
_SAMPLE_FORMATS = {16: "s16p", 24: "s32p", 32: "s32p"}


def _network_options(config: Config) -> dict[str, str]:
    """Return yt-dlp network options derived from the application config."""
    if config.force_ipv4:
        # yt-dlp's --force-ipv4 maps to source_address="0.0.0.0".
        return {"source_address": "0.0.0.0"}
    return {}


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


def _video_id_from_url(url: str) -> str | None:
    """URL から動画 ID を取り出す。"""
    match = re.search(r"[?&]v=([^&#]+)", url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        video_id = parsed.path.strip("/")
        return video_id or None
    return None


def _archive_contains(config: Config, video_id: str | None) -> bool:
    """download archive に動画 ID が記録済みかを確認する。"""
    if not video_id:
        return False
    archive_file = config.archive_file
    if not archive_file.is_file():
        return False
    try:
        text = archive_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    pattern = re.compile(rf"^youtube {re.escape(video_id)}$", re.M)
    return pattern.search(text) is not None


def _single_video_url(url: str) -> str:
    """list と index を除いた単体動画 URL を作る。"""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query.pop("list", None)
    query.pop("index", None)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _resolve_playlist_item_selection(url: str) -> tuple[str | None, str]:
    """index 付きプレイリスト URL の対象曲を判定する。
    list と index の両方がある場合、その index（1始まり）の1曲だけを
    ダウンロード対象とする。index が不正な場合は警告を出して
    v の単体動画 URL へフォールバックする。
    """
    parsed = urlparse(url)
    query = parse_qsl(parsed.query)
    values = dict(query)
    if not values.get("v") or not values.get("list"):
        return None, url
    index_values = [value for key, value in query if key == "index"]
    if not index_values:
        return None, url
    if len(index_values) != 1:
        logger.warning(
            "プレイリストの index が複数指定されています: %s。"
            "単体動画としてダウンロードします。",
            ",".join(index_values),
        )
        return None, _single_video_url(url)
    index = index_values[0]
    if not index.isdigit() or int(index) < 1:
        logger.warning(
            "プレイリストの index が不正です: %s。"
            "単体動画としてダウンロードします。",
            index,
        )
        return None, _single_video_url(url)
    return index, url


def _prepare_entry(
    entry: dict[str, Any],
    mode: str,
    config: Config,
) -> None:
    if mode != "audio":
        return
    naming = build_audio_name(entry)
    entry["title"] = naming["filename"]
    if config.genre_lookup and naming["track"] and naming["artist"]:
        try:
            genre = lookup_genre(
                naming["track"],
                naming["artist"],
            )
        except Exception as exc:
            logger.warning(
                "MusicBrainz のジャンル照合に失敗しました: %s",
                exc,
            )
            genre = None
        if genre:
            entry["genre"] = genre
            entry["genres"] = [genre]
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
    if entries is not None:
        # entries は遅延評価の PlaylistEntries の可能性があるため、
        # list 化して実体化してから各 entry に命名を適用する。
        materialized = list(entries)
        info["entries"] = materialized
        for entry in materialized:
            if isinstance(entry, dict):
                _prepare_entry(entry, mode, config)
        return
    # プレイリスト本体には音声命名を適用しない。
    if info.get("_type") in ("playlist", "multi_video"):
        return
    _prepare_entry(info, mode, config)


_STREAMHASH_RE = re.compile(r"SHA256=([0-9a-fA-F]{64})")


def parse_streamhash(output: str) -> str | None:
    """ffmpeg streamhash の出力から SHA-256 を取得する。"""
    match = _STREAMHASH_RE.search(output)
    if not match:
        return None
    return match.group(1).lower()


def _calculate_audio_stream_hash(
    ffmpeg: str,
    filepath: Path,
) -> str | None:
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-v", "error",
                "-i", str(filepath),
                "-map", "0:a:0",
                "-f", "streamhash",
                "-hash", "sha256",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        logger.warning(
            "音声ストリームハッシュの計算に失敗しました: %s: %s",
            filepath,
            exc,
        )
        return None
    if result.returncode != 0:
        logger.warning(
            "音声ストリームハッシュの計算に失敗しました: %s: %s",
            filepath,
            result.stderr.strip(),
        )
        return None
    return parse_streamhash(result.stdout)


def _embed_audio_stream_hash(
    ffmpeg: str,
    filepath: Path,
    stream_hash: str,
) -> None:

    with tempfile.NamedTemporaryFile(
        suffix=filepath.suffix,
        dir=filepath.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-v", "error",
                "-i", str(filepath),
                "-map", "0",
                "-codec", "copy",
                "-metadata",
                f"AUDIO_STREAM_SHA256={stream_hash}",
                "-y",
                str(temporary),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "音声ストリームハッシュの埋め込みに失敗しました: %s: %s",
                filepath,
                result.stderr.strip(),
            )
            return
        temporary.replace(filepath)
    except OSError as exc:
        logger.warning(
            "音声ストリームハッシュの埋め込みに失敗しました: %s: %s",
            filepath,
            exc,
        )
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _record_audio_stream_hash(
    filepath: Path,
    config: Config,
) -> None:
    ffmpeg = _get_ffmpeg_location(config)
    if not ffmpeg:
        return
    if not filepath.is_file():
        logger.warning(
            "音声ファイルが見つからないためハッシュを記録できません: %s",
            filepath,
        )
        return
    stream_hash = _calculate_audio_stream_hash(ffmpeg, filepath)
    if stream_hash is None:
        return
    _embed_audio_stream_hash(
        ffmpeg,
        filepath,
        stream_hash,
    )


def _requested_audio_paths(info: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for item in info.get("requested_downloads") or []:
        if not isinstance(item, dict):
            continue
        filepath = item.get("filepath")
        if isinstance(filepath, str) and filepath:
            paths.append(Path(filepath))
    return paths



def _build_output_template(
    config: Config,
    mode: str,
    info: dict[str, Any],
) -> str:
    if mode == "audio":
        mode_dir = "audio"
    else:
        mode_dir = "video"
    if info.get("_type") in ("playlist", "multi_video"):
        playlist = info.get("title") or info.get("uploader") or "playlist"
        safe_title = sanitize_filename(str(playlist))
        base_dir = config.download_dir / mode_dir / safe_title or config.download_dir / mode_dir
        if mode == "audio":
            return str(base_dir / "%(playlist_index)02d - %(title)s.%(ext)s")
        return str(base_dir / "%(playlist_index)02d - %(title)s.%(ext)s")
    return str(config.download_dir / mode_dir / "%(title)s.%(ext)s")


def _build_options(
    config: Config,
    output_template: str,
    mode: str,
    download: bool = False,
    extraction_only: bool = False,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "outtmpl": output_template,
        "logger": YTDLPLogger(),
        "progress_hooks": [_progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "ignoreerrors": True,
        "no_color": True,
        "restrictfilenames": False,
    }
    options.update(_network_options(config))
    ffmpeg = _get_ffmpeg_location(config)
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg
    if config.archive_file:
        options["download_archive"] = str(config.archive_file)
    if mode == "audio":
        options["format"] = "bestaudio/best"
        if config.audio_format == "mp3":
            postprocessors: list[dict[str, Any]] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(config.audio_bitrate),
                },
            ]
            audio_args: list[str] = []
            if config.audio_bit_depth is not None:
                sample_format = _SAMPLE_FORMATS.get(
                    config.audio_bit_depth,
                    "s16p",
                )
                audio_args += [
                    "-sample_fmt",
                    sample_format,
                ]
            if config.audio_sample_rate is not None:
                audio_args += [
                    "-ar",
                    str(config.audio_sample_rate),
                ]
            if audio_args:
                options["postprocessor_args"] = {
                    "FFmpegExtractAudio": audio_args,
                }
            elif config.embed_metadata:
                postprocessors.append({"key": "FFmpegMetadata"})
            if config.embed_album_art:
                postprocessors.append(
                    {
                        "key": "EmbedThumbnail",
                        "already_have_thumbnail": False,
                    },
                )
            options["postprocessors"] = postprocessors
        else:
            postprocessors = []
            if config.embed_metadata:
                postprocessors.append({"key": "FFmpegMetadata"})
            if config.embed_album_art:
                postprocessors.append(
                    {
                        "key": "EmbedThumbnail",
                        "already_have_thumbnail": False,
                    },
                )
            if postprocessors:
                options["postprocessors"] = postprocessors
    else:
        options["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        if config.embed_metadata:
            options["postprocessors"] = [{"key": "FFmpegMetadata"}]
    if config.subtitles:
        options["writesubtitles"] = True
        options["subtitleslangs"] = ["ja", "en"]
    if config.thumbnails:
        options["writethumbnail"] = True
    if extraction_only:
        options["skip_download"] = True
    return options


def _cleanup_embed_thumbnails(
    config: Config,
    output_template: str,
    mode: str,
) -> None:
    if mode != "audio" or not config.embed_album_art:
        return
    output_path = Path(output_template)
    directory = output_path.parent
    if not directory.exists():
        return
    for thumbnail in directory.glob("*.webp"):
        try:
            thumbnail.unlink()
        except OSError:
            logger.warning(
                "サムネイルの削除に失敗しました: %s",
                thumbnail,
            )
    for thumbnail in directory.glob("*.jpg"):
        try:
            thumbnail.unlink()
        except OSError:
            logger.warning(
                "サムネイルの削除に失敗しました: %s",
                thumbnail,
            )


def download(url: str, mode: str, config: Config) -> None:
    if mode not in ("video", "audio"):
        raise ValueError(f"不正なモードです: {mode}")
    if not url or not url.strip():
        raise ValueError("URLを指定してください。")
    config.download_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "YTB downloader v%s started. yt-dlp version=%s",
        APP_VERSION,
        yt_dlp.version.__version__,
    )
    try:
        playlist_item, download_url = _resolve_playlist_item_selection(url)
        extraction_options = _build_options(
            config,
            "%(title)s.%(ext)s",
            mode,
            extraction_only=True,
        )
        with yt_dlp.YoutubeDL(extraction_options) as extract_ydl:
            info = extract_ydl.extract_info(download_url, download=False)
        if info is None:
            video_id = _video_id_from_url(download_url)
            if _archive_contains(config, video_id):
                logger.info("すべて取得済みです。")
                return
            raise RuntimeError("抽出に失敗しました。")
        if info.get("_type") == "channel":
            raise ValueError("チャンネルURLには対応していません。")
        _prepare_entries(info, mode, config)
        entries = info.get("entries")
        if entries is not None and len(list(entries)) == 0:
            logger.info("すべて取得済みです。")
            return
        if playlist_item is not None:
            playlist_entries = list(entries or [])
            playlist_size = len(playlist_entries)
            item_number = int(playlist_item)
            if item_number > playlist_size or item_number < 1:
                logger.warning(
                    "指定された index %s はプレイリストの範囲外です。"
                    "単体動画としてダウンロードします。",
                    playlist_item,
                )
                single_url = _single_video_url(url)
                download(single_url, mode, config)
                return
            entry = playlist_entries[item_number - 1]
            if isinstance(entry, dict):
                video_id = entry.get("id") or _video_id_from_url(url)
                if _archive_contains(config, video_id):
                    logger.info("すべて取得済みです。")
                    return
        output_template = _build_output_template(config, mode, info)
        download_options = _build_options(
            config,
            output_template,
            mode,
            download=True,
        )
        with yt_dlp.YoutubeDL(download_options) as download_ydl:
            try:
                result = download_ydl.process_ie_result(info, download=True)
            except EntryNotInPlaylist:
                logger.info("すべて取得済みです。")
                return
            if result is None:
                logger.warning("ダウンロード結果が取得できませんでした。")
            else:
                logger.info("ダウンロード処理が完了しました。")
            if mode == "audio" and config.record_audio_hash:
                for filepath in _requested_audio_paths(info):
                    try:
                        _record_audio_stream_hash(filepath, config)
                    except Exception as exc:
                        logger.warning(
                            "音声ストリームハッシュの記録に失敗しました: %s: %s",
                            filepath,
                            exc,
                        )
        _cleanup_embed_thumbnails(config, output_template, mode)
    except Exception as exc:
        if "HTTP Error 403" in str(exc):
            logger.error(
                "HTTP 403 エラーが発生しました。YouTube側の制限の可能性があります。"
                "force_ipv4 を有効にすると回避できる場合があります。",
            )
        logger.exception("ダウンロードに失敗しました。")
        raise
