"""Windows のクリップボード読取と YouTube URL 抽出。"""

from __future__ import annotations

import re

try:
    import win32clipboard
except ImportError:
    win32clipboard = None

# クリップボードに貼り付けられたテキストから YouTube URL を抽出する。
# youtube.com / music.youtube.com / youtu.be の形式を対象とする。
_YOUTUBE_URL_RE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*youtube\.com[^\s]*"
    r"|https?://(?:[a-z0-9-]+\.)*youtu\.be[^\s]*"
)

# 末尾に続く文字（文末の「。」「、」など）をURLから除去する。
_TRAILING_TRIM = ".,;:!?\"'。、）】』（"


def get_clipboard_text() -> str | None:
    """クリップボードのテキストを取得する（Windows のみ）。

    Unicodeテキストが取得できればそれ、ANSIテキストが取得できればそれを返す。
    クリップボードが空・アクセス不可の場合は None を返す。
    """
    if win32clipboard is None:
        return None
    try:
        win32clipboard.OpenClipboard(None)
        try:
            for fmt in (win32clipboard.CF_UNICODETEXT, win32clipboard.CF_TEXT):
                try:
                    return win32clipboard.GetClipboardData(fmt)
                except Exception:
                    continue
            return None
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return None


def find_youtube_url(text: str | None) -> str | None:
    """テキストから YouTube URL を抽出する（見つからない場合は None）。

    最初に出現する YouTube URL（左端優先）を返す。末尾の
    句読点などは除去する。
    """
    if not text:
        return None
    match = _YOUTUBE_URL_RE.search(text)
    if not match:
        return None
    url = match.group(0).strip()
    while url and url[-1] in _TRAILING_TRIM:
        url = url[:-1]
    return url or None
