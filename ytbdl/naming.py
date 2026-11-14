from __future__ import annotations

import re
import unicodedata
from typing import Any


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_FEAT_PATTERN = re.compile(
    r"\b(?:feat(?:uring)?\.?|ft\.?)\s*",
    re.IGNORECASE,
)
_REMIX_PATTERN = re.compile(
    r"\(([^()]*(?:remix|mix)[^()]*)\)",
    re.IGNORECASE,
)
_COVER_PATTERN = re.compile(
    r"歌ってみた|cover|カバー",
    re.IGNORECASE,
)
_COVER_BY_PATTERN = re.compile(
    r"(?:covered\s+by|cover\s+by)\s*[:：]?\s*(.+)$",
    re.IGNORECASE,
)
_COVER_SUNG_PATTERN = re.compile(
    r"歌ってみた\s*[:：]\s*(.+)$",
)
_ARTIST_SEPARATOR = re.compile(r"\s+-\s+")
_TRAILING_NOISE = re.compile(
    r"\s*[\[(（【].*?"
    r"(?:official|music video|lyric video|lyrics|mv|pv|"
    r"高音質|公式|オフィシャル|歌詞).*?"
    r"[\])）】]\s*$",
    re.IGNORECASE,
)


def sanitize_filename(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value))
    value = _INVALID_FILENAME_CHARS.sub("_", value)
    value = _WHITESPACE.sub(" ", value)
    value = value.strip(" .")
    if not value:
        value = "untitled"

    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if value.split(".")[0].upper() in reserved:
        value = f"_{value}"
    return value


def normalize_feat(text: str) -> str:
    """
    feat. / ft. / featuring を feat. に統一する。
    既存の括弧表記を維持する。
    """
    text = _FEAT_PATTERN.sub("feat. ", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()


def extract_feat(text: str) -> tuple[str, str]:
    """
    曲名からfeat表記を取り出す。

    Returns:
        (featを除いた曲名, feat部分)
    """
    text = normalize_feat(text)
    match = re.search(
        r"\bfeat\.\s*(.+)$",
        text,
        re.IGNORECASE,
    )
    if not match:
        return text.strip(), ""
    feat_artists = match.group(1).strip()
    track = text[: match.start()].strip()
    if feat_artists.startswith("("):
        feat_artists = feat_artists[1:]
    if feat_artists.endswith(")"):
        feat_artists = feat_artists[:-1]
    return track, f"(feat. {feat_artists})"


def extract_remixes(text: str) -> tuple[str, list[str]]:
    """
    曲名からRemix表記を抽出する。
    複数のRemix表記に対応する。
    """
    remixes = [
        f"({match.group(1).strip()})"
        for match in _REMIX_PATTERN.finditer(text)
    ]
    remaining = _REMIX_PATTERN.sub("", text)
    remaining = _WHITESPACE.sub(" ", remaining).strip()
    return remaining, remixes


def is_cover(title: str) -> bool:
    return bool(_COVER_PATTERN.search(title))


def _clean_track_title(title: str) -> str:
    title = _TRAILING_NOISE.sub("", title)
    title = re.sub(r"^[【\[(（].*?[】\])）]\s*", "", title)
    title = re.sub(
        r"\s*[-/|]\s*(?:official|lyrics?|music video|mv)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return _WHITESPACE.sub(" ", title).strip(" -/|")


def _extract_cover_artist(
    title: str,
    uploader: str,
) -> str:
    match = (
        _COVER_BY_PATTERN.search(title)
        or _COVER_SUNG_PATTERN.search(title)
    )
    if match:
        artist = match.group(1).strip()
        artist = re.split(
            r"\s*[/|｜]\s*|\s+-\s+",
            artist,
            maxsplit=1,
        )[0]
        artist = re.sub(r"^[\[【（(\])）】\s]+", "", artist)
        artist = re.sub(r"[\])）】]+$", "", artist).strip()
        if artist:
            return artist
    return uploader.strip()


def _parse_title(
    title: str,
    uploader: str,
) -> tuple[str, str]:
    """
    タイトルを解析して (曲名, アーティスト) を返す。
    """
    clean = _clean_track_title(title)
    if not clean:
        return "", ""
    if is_cover(title):
        artist = _extract_cover_artist(title, uploader)
        track = clean
        track = re.split(
            r"\s*[/|｜]?\s*(?:covered|cover)\s+by\s+",
            track,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        track = re.sub(
            r"[\[(（【]\s*(?:歌ってみた|cover|カバー)\s*[\])）】]",
            "",
            track,
            flags=re.IGNORECASE,
        )
        track = re.sub(
            r"\s+(?:歌ってみた|カバー)\s*$",
            "",
            track,
            flags=re.IGNORECASE,
        )
        track = re.sub(r"\s+", " ", track).strip(" -/|")
        if not track:
            track = clean
        return track, artist
    separator = _ARTIST_SEPARATOR.search(clean)
    if separator:
        first = clean[: separator.start()].strip()
        second = clean[separator.end():].strip()
        if first and second:
            # 「アーティスト - 曲名」を優先する。
            return second, first
    return clean, uploader.strip()


def build_audio_name(info: dict[str, Any]) -> dict[str, Any]:
    title = str(info.get("title") or "").strip()
    uploader = str(info.get("uploader") or "").strip()
    metadata_track = str(info.get("track") or "").strip()
    metadata_artist = str(
        info.get("artist")
        or info.get("artists")
        or ""
    ).strip()
    cover = is_cover(title)
    original_artist = metadata_artist
    if metadata_track and metadata_artist:
        track = metadata_track
        artist = metadata_artist
    else:
        track, artist = _parse_title(title, uploader)
    if metadata_track:
        track = metadata_track
    if metadata_artist and not cover:
        artist = metadata_artist
    if cover:
        artist = _extract_cover_artist(title, uploader)
    if not track:
        return {
            "filename": sanitize_filename(title),
            "track": title,
            "artist": artist,
            "album_artist": original_artist,
            "cover": cover,
        }
    track = _clean_track_title(track)
    track, remixes = extract_remixes(track)
    track, feat = extract_feat(track)
    parts = [track]
    if feat:
        parts.append(feat)
    parts.extend(remixes)
    if cover:
        parts.append("(Cover)")
    filename = " ".join(part for part in parts if part)
    if artist:
        filename = f"{filename} - {artist}"
    return {
        "filename": sanitize_filename(filename),
        "track": track,
        "artist": artist,
        "album_artist": original_artist,
        "cover": cover,
    }


def build_video_name(info: dict[str, Any]) -> str:
    title = str(info.get("title") or "untitled")
    video_id = str(info.get("id") or "unknown")
    return sanitize_filename(f"{title} [{video_id}]")


def build_audio_filename(info: dict[str, Any]) -> str:
    return build_audio_name(info)["filename"]
