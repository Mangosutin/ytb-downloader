"""ダウンロードキュー（スタック）。

FIFO 順に1件ずつ順次実行するワーカースレッドと、キュー状態への
通知は排他制御されたロックで安全に行う。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from ytbdl.cli import resolve_url
from ytbdl.config import Config
from ytbdl.core import _archive_contains, _video_id_from_url, download

logger = logging.getLogger(__name__)


@dataclass
class DownloadRequest:
    """キューに積まれた1件のダウンロード指示。"""

    url: str
    mode: str
    description: str = ""
    # "list" (プレイリスト) / "single" (単体) / None (未解決)
    kind: str | None = None
    video_id: str | None = None
    title: str | None = None
    priority: int = 0
    done: bool = False
    skipped: bool = False
    error: str | None = None


@dataclass(frozen=True)
class QueueStatus:
    """キュー状態のスナップショット。"""

    running: DownloadRequest | None
    queued: tuple[DownloadRequest, ...]
    paused: bool


def describe_item(req: DownloadRequest) -> str:
    """キュー表示用の文字列（例: `audio | 単体 | タイトル [abc123]`）。"""
    if req.kind == "list":
        kind_label = "プレイリスト"
    elif req.kind == "single":
        kind_label = "単体"
    else:
        kind_label = ""
    title = req.title or req.description or req.url
    video = f" [{req.video_id}]" if req.video_id else ""
    if kind_label:
        return f"{req.mode} | {kind_label} | {title}{video}"
    return f"{req.mode} | {title}{video}"


class DownloadQueue:
    """FIFO のダウンロードキュー。

    `enqueue(url, mode)` でキューに積む。`priority=1` のものは
    キュー先頭に積まれる（Run now 用）。
    """

    def __init__(
        self,
        config: Config,
        status_callback=None,
        download_func=None,
    ):
        self._config = config
        # ワーカースレッドからUIスレッドへ状態を通知するコールバック
        self.status_callback = status_callback
        self._download_func = download_func if download_func is not None else download
        self._lock = threading.Lock()
        self._queue: list[DownloadRequest] = []
        self._paused = False
        self._stop = threading.Event()
        self._new_items = threading.Event()
        self._worker: threading.Thread | None = None
        self._running: DownloadRequest | None = None

    # ------------------------------------------------------------------
    # ワーカースレッド

    def start(self) -> None:
        if self._worker is not None:
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="ytbdl-queue",
            daemon=True,
        )
        self._worker.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        self._new_items.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout)
        self._worker = None

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            item = self.pop_next()
            if item is None:
                self._new_items.wait(0.2)
                self._new_items.clear()
                self._emit_status()
                continue
            try:
                self._run(item)
            finally:
                with self._lock:
                    if self._running is item:
                        self._running = None
                    item.done = True
                self._emit_status()

    def _run(self, item: DownloadRequest) -> None:
        url = resolve_url(item.url)
        try:
            video_id = _video_id_from_url(url)
            if _archive_contains(self._config, video_id):
                item.skipped = True
                logger.info("アーカイブ済みのためスキップします: %s", url)
                return
            self._download_func(
                url,
                item.mode,
                self._config,
                info_callback=lambda info: self._on_info(item, info),
            )
        except Exception as exc:
            item.error = str(exc)
            logger.exception("キューの処理に失敗しました: %s", url)

    def _on_info(self, item: DownloadRequest, info: dict) -> None:
        with self._lock:
            item.kind = (
                "list"
                if info.get("_type") in ("playlist", "multi_video")
                else "single"
            )
            item.title = str(info.get("title") or "")
            item.video_id = _video_id_from_url(item.url) or str(
                info.get("id") or ""
            )
        self._emit_status()

    # ------------------------------------------------------------------
    # 公開API（UIスレッドから呼ぶ）

    def enqueue(
        self,
        url: str,
        mode: str,
        priority: int = 0,
    ) -> DownloadRequest:
        """キューに追加する。priority=1 は先頭に積む。"""
        req = DownloadRequest(
            url=url,
            mode=mode,
            priority=priority,
            description=url,
        )
        with self._lock:
            if priority:
                self._queue.insert(0, req)
            else:
                self._queue.append(req)
        self._emit_status()
        self._new_items.set()
        return req

    def pop_next(self) -> DownloadRequest | None:
        """次に実行する項目をキューから取り出す（空・一時停止時はNone）。"""
        with self._lock:
            if self._paused or not self._queue:
                return None
            item = self._queue.pop(0)
            self._running = item
            return item

    def clear(self) -> int:
        """未実行の項目を全て削除し、削除した件数を返す。"""
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
        self._emit_status()
        return count

    def remove(self, req: DownloadRequest) -> bool:
        """指定した未実行項目を削除する。削除した場合はTrueを返す。"""
        with self._lock:
            try:
                self._queue.remove(req)
                found = True
            except ValueError:
                found = False
        if found:
            self._emit_status()
        return found

    def pause(self) -> None:
        with self._lock:
            self._paused = True
        self._emit_status()

    def resume(self) -> None:
        with self._lock:
            self._paused = False
        self._new_items.set()
        self._emit_status()

    def status(self) -> QueueStatus:
        """キュー状態のスナップショットを返す。"""
        with self._lock:
            return QueueStatus(
                running=self._running,
                queued=tuple(self._queue),
                paused=self._paused,
            )

    # ------------------------------------------------------------------
    # 内部

    def _emit_status(self) -> None:
        if self.status_callback is None:
            return
        try:
            self.status_callback(self.status())
        except Exception:
            logger.debug("ステータス通知に失敗しました", exc_info=True)
