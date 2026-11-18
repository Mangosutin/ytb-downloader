"""MusicBrainz API を利用した音楽ジャンル照合。"""
from __future__ import annotations


import json
import logging
import time
from typing import Any, Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


from ytbdl import APP_VERSION


logger = logging.getLogger(__name__)


_API_BASE = "https://musicbrainz.org/ws/2"
_USER_AGENT = f"YTB-downloader/{APP_VERSION} (MusicBrainz genre lookup)"
_MIN_REQUEST_INTERVAL = 1.0


_last_request_time = 0.0


def _request_json(url: str) -> dict:
    global _last_request_time


    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)


    request = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            data = json.load(response)
    finally:
        _last_request_time = time.monotonic()


    if not isinstance(data, dict):
        raise ValueError("MusicBrainz API の応答形式が不正です")
    return data


def _recording_ids(search_result: dict[str, Any]) -> list[str]:
    """検索結果から上位5件の recording MBID を取得する。"""
    recordings = search_result.get("recordings", [])
    result: list[str] = []
    for recording in recordings[:5]:
        if not isinstance(recording, dict):
            continue
        recording_id = recording.get("id")
        if isinstance(recording_id, str) and recording_id:
            result.append(recording_id)
    return result


def _sorted_genres(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    values = [
        item
        for item in items
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    values.sort(key=lambda item: int(item.get("count", 0)), reverse=True)
    return [str(item["name"]) for item in values]


def _recording_genre(
    detail: dict[str, Any],
    request_json: Callable[[str], dict[str, Any]],
) -> str | None:
    genres = _sorted_genres(detail.get("genres"))
    if genres:
        return genres[0]
    for release in detail.get("releases", []):
        if not isinstance(release, dict):
            continue
        group = release.get("release-group")
        if not isinstance(group, dict):
            continue
        group_id = group.get("id")
        if not isinstance(group_id, str) or not group_id:
            continue
        group_detail = request_json(
            f"{_API_BASE}/release-group/{quote(group_id)}?inc=genres&fmt=json"
        )
        genres = _sorted_genres(group_detail.get("genres"))
        if genres:
            return genres[0]
    for credit in detail.get("artist-credit", []):
        if not isinstance(credit, dict):
            continue
        artist = credit.get("artist")
        if not isinstance(artist, dict):
            continue
        artist_id = artist.get("id")
        if not isinstance(artist_id, str) or not artist_id:
            continue
        artist_detail = request_json(
            f"{_API_BASE}/artist/{quote(artist_id)}?inc=genres&fmt=json"
        )
        genres = _sorted_genres(artist_detail.get("genres"))
        if genres:
            return genres[0]
        tags = _sorted_genres(artist_detail.get("tags"))
        if tags:
            return tags[0]
    return None


def lookup_genre(track: str, artist: str) -> str | None:
    """MusicBrainz から曲のジャンルを照合する。"""
    if not track or not artist:
        return None
    try:
        query = urlencode({
            "query": f'recording:"{track}" AND artistname:"{artist}"',
            "fmt": "json",
            "limit": "5",
        })
        data = _request_json(f"{_API_BASE}/recording?{query}")
        recording_ids = _recording_ids(data)
        for recording_id in recording_ids:
            detail = _request_json(
                f"{_API_BASE}/recording/{quote(recording_id)}"
                "?fmt=json&inc=genres+releases"
            )
            genre = _recording_genre(detail, _request_json)
            if genre:
                return genre
    except Exception as exc:
        logger.warning(
            "MusicBrainz のジャンル照合に失敗しました: %s",
            exc,
        )
    return None
