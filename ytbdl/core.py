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
    playlist_item: str | None = None,
    extraction_only: bool = False,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "outtmpl": {
            "default": output_template,
        },
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
        **_network_options(config),
    }
    if not extraction_only:
        # download_archive はダウンロード用のインスタンスでのみ有効化する。
        # 抽出時に含めると、アーカイブ済みエントリが抽出段階で除外される。
        options["download_archive"] = str(config.archive_file)
    if playlist_item is not None:
        options["playlist_items"] = playlist_item
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
        postprocessors: list[dict[str, Any]] = []
        if config.audio_format == "mp3":
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(config.audio_bitrate),
            })
            if config.embed_album_art:
                # アルバムアート埋め込みにはサムネイル取得が必要。
                options["writethumbnail"] = True
                postprocessors.append({"key": "EmbedThumbnail"})
            if config.embed_metadata:
                postprocessors.append({
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                })
        audio_args: list[str] = []
        if config.audio_sample_rate is not None:
            audio_args += ["-ar", str(config.audio_sample_rate)]
        if config.audio_bit_depth is not None:
            audio_args += [
                "-sample_fmt",
                _SAMPLE_FORMATS[config.audio_bit_depth],
            ]
        if audio_args:
            options["postprocessor_args"] = {
                "FFmpegExtractAudio": audio_args,
            }
        elif config.embed_metadata:
            postprocessors.append({
                "key": "FFmpegMetadata",
                "add_metadata": True,
            })
        if postprocessors:
            options["postprocessors"] = postprocessors

    return options


def _cleanup_embed_thumbnails(
    config: Config,
    output_template: str,
    mode: str,
) -> None:
    """埋め込み用の一時サムネイルを削除する。"""
    if mode != "audio":
        return
    if not config.embed_album_art or config.thumbnails:
        return
    output_dir = Path(output_template).parent
    targets: list[Path] = []
    for pattern in ("*.jpg", "*.jpeg", "*.webp", "*.png"):
        targets += list(output_dir.glob(pattern))
        if output_dir != config.download_dir:
            targets += list(config.download_dir.glob(pattern))
    for target in targets:
        try:
            target.unlink()
        except OSError:
            logger.debug(
                "サムネイルの削除に失敗しました: %s",
                target,
            )


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
    logger.info(
        "IPv4固定: %s",
        "有効" if config.force_ipv4 else "無効",
    )
    yt_dlp_version = getattr(
        getattr(yt_dlp, "version", None),
        "__version__",
        "unknown",
    )
    logger.info("yt-dlp version: %s", yt_dlp_version)
    if mode == "audio":
        logger.info("音声形式: %s", config.audio_format)
    try:
        # index 付きプレイリスト URL の対象曲を判定する。
        # 不正な index はここで単体動画 URL へフォールバックする。
        playlist_item, download_url = _resolve_playlist_item_selection(url)
        placeholder_template = str(
            config.download_dir / "%(title)s.%(ext)s"
        )
        extraction_options = _build_options(
            config,
            mode,
            placeholder_template,
            extraction_only=True,
        )
        with yt_dlp.YoutubeDL(extraction_options) as extract_ydl:
            info = extract_ydl.extract_info(
                download_url,
                download=False,
            )
            if not info:
                if _archive_contains(config, _video_id_from_url(download_url)):
                    logger.info("すべて取得済みです。")
                    return
                raise RuntimeError(
                    "動画情報を取得できませんでした。"
                )
            if info.get("_type") == "channel":
                raise ValueError(
                    "チャンネル全動画の一括ダウンロードには対応していません。"
                )
            _prepare_entries(info, mode, config)
            if info.get("_type") in ("playlist", "multi_video") and not info.get(
                "entries"
            ):
                logger.info("すべて取得済みです。")
                return
            if playlist_item is not None and info.get("_type") in (
                "playlist",
                "multi_video",
            ):
                entries = info.get("entries") or []
                total = info.get("playlist_count") or len(entries)
                index_number = int(playlist_item)
                if total and index_number > total:
                    logger.warning(
                        "プレイリストの index が範囲外です: %s（全%s件）。"
                        "単体動画としてダウンロードします。",
                        playlist_item,
                        total,
                    )
                    playlist_item = None
                    download_url = _single_video_url(url)
                    info = extract_ydl.extract_info(
                        download_url,
                        download=False,
                    )
                    if not info:
                        if _archive_contains(
                            config, _video_id_from_url(download_url)
                        ):
                            logger.info("すべて取得済みです。")
                            return
                        raise RuntimeError(
                            "動画情報を取得できませんでした。"
                        )
                    _prepare_entries(info, mode, config)
                elif entries and index_number <= len(entries):
                    selected = entries[index_number - 1]
                    if isinstance(selected, dict) and _archive_contains(
                        config, selected.get("id")
                    ):
                        logger.info("すべて取得済みです。")
                        return
            output_template = _build_output_template(
                info,
                mode,
                config,
            )
        download_options = _build_options(
            config,
            mode,
            output_template,
            playlist_item=playlist_item,
        )
        with yt_dlp.YoutubeDL(download_options) as download_ydl:
            try:
                result = download_ydl.process_ie_result(
                    info,
                    download=True,
                )
            except EntryNotInPlaylist:
                logger.info("すべて取得済みです。")
                return
            if result is None:
                logger.warning(
                    "ダウンロード対象がありませんでした。"
                )
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
                "YouTubeからメディアデータを取得できませんでした（HTTP 403）。"
            )
            if config.force_ipv4:
                logger.error(
                    "IPv4固定は有効です。yt-dlpの更新状況、動画の配信条件、"
                    "PO Token関連の要件、ネットワーク側の拒否を確認してください。"
                )
            else:
                logger.error(
                    "IPv4固定は無効です。config.tomlのforce_ipv4 = trueを"
                    "試してください。"
                )
        logger.exception("ダウンロードに失敗しました。")
        raise
