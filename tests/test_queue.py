import threading
import time
from pathlib import Path

from ytbdl.config import Config
from ytbdl.queue import DownloadQueue, DownloadRequest, describe_item


def _make_config(tmp_path: Path) -> Config:
    return Config(
        download_dir=tmp_path / "downloads",
        archive_file=tmp_path / "archive.txt",
        log_dir=tmp_path / "logs",
        default_mode="audio",
        audio_format="mp3",
        ffmpeg_location=tmp_path / "ffmpeg",
        force_ipv4=True,
        subtitles=False,
        thumbnails=False,
        embed_metadata=False,
        cookies=None,
    )


def _wait_until(cond, timeout: float = 5.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(interval)
    return cond()


class _FakeDownload:
    """Worker スレッドで呼ばれるダウンロード関数のフェイク。"""

    def __init__(self, delay: float = 0.0, fail: bool = False):
        self.delay = delay
        self.fail = fail
        self.calls: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def __call__(self, url, mode, config, info_callback=None):
        if self.delay:
            time.sleep(self.delay)
        with self._lock:
            self.calls.append((url, mode))
        if info_callback is not None:
            info_callback(
                {
                    "_type": "video",
                    "title": f"Title of {url}",
                    "id": "abc123",
                }
            )
        if self.fail:
            raise ValueError("boom")


def test_enqueue_appends_in_fifo_order(tmp_path) -> None:
    q = DownloadQueue(_make_config(tmp_path))
    q.enqueue("https://a", "audio")
    q.enqueue("https://b", "video", priority=1)
    status = q.status()
    assert status.running is None
    assert [item.url for item in status.queued] == ["https://b", "https://a"]


def test_pop_next_returns_none_when_empty(tmp_path) -> None:
    q = DownloadQueue(_make_config(tmp_path))
    assert q.pop_next() is None


def test_pop_next_returns_none_when_paused(tmp_path) -> None:
    q = DownloadQueue(_make_config(tmp_path))
    q.pause()
    assert q.pop_next() is None
    assert q.status().paused is True
    q.resume()
    assert q.status().paused is False


def test_run_now_goes_to_front(tmp_path) -> None:
    q = DownloadQueue(_make_config(tmp_path))
    q.enqueue("https://a", "audio")
    req = q.enqueue("https://b", "audio", priority=1)
    assert q.pop_next() is req
    assert q.pop_next().url == "https://a"
    assert q.pop_next() is None


def test_clear_returns_count(tmp_path) -> None:
    q = DownloadQueue(_make_config(tmp_path))
    q.enqueue("https://a", "audio")
    q.enqueue("https://b", "audio")
    assert q.clear() == 2
    assert q.status().queued == ()


def test_remove_by_request(tmp_path) -> None:
    q = DownloadQueue(_make_config(tmp_path))
    req = q.enqueue("https://a", "audio")
    assert q.remove(req) is True
    assert q.remove(req) is False
    assert q.status().queued == ()


def test_worker_processes_items_sequentially(tmp_path) -> None:
    fake = _FakeDownload(delay=0.05)
    q = DownloadQueue(_make_config(tmp_path), download_func=fake)
    q.start()
    try:
        q.enqueue("https://a", "audio")
        q.enqueue("https://b", "audio")
        assert _wait_until(lambda: len(fake.calls) == 2)
        assert [url for url, _ in fake.calls] == ["https://a", "https://b"]
    finally:
        q.stop()


def test_worker_captures_download_errors(tmp_path) -> None:
    fake = _FakeDownload(fail=True)
    q = DownloadQueue(_make_config(tmp_path), download_func=fake)
    q.start()
    try:
        req = q.enqueue("https://a", "audio")
        assert _wait_until(lambda: req.done)
        assert "boom" in req.error
    finally:
        q.stop()


def test_worker_sets_item_fields_from_info(tmp_path) -> None:
    fake = _FakeDownload()
    q = DownloadQueue(_make_config(tmp_path), download_func=fake)
    q.start()
    try:
        req = q.enqueue("https://a", "audio")
        assert _wait_until(lambda: req.done)
        assert req.kind == "single"
        assert req.title == "Title of https://a"
        assert req.video_id == "abc123"
    finally:
        q.stop()


def test_status_snapshot_shape(tmp_path) -> None:
    q = DownloadQueue(_make_config(tmp_path))
    req = q.enqueue("https://a", "audio")
    status = q.status()
    assert status.running is None
    assert list(status.queued) == [req]
    assert status.paused is False


def test_describe_item_with_title_and_id() -> None:
    req = DownloadRequest(
        url="u",
        mode="audio",
        kind="single",
        title="タイトル",
        video_id="abc123",
    )
    assert describe_item(req) == "audio | 単体 | タイトル [abc123]"


def test_describe_item_without_title_falls_back_to_url() -> None:
    req = DownloadRequest(url="u", mode="video", kind=None)
    assert describe_item(req) == "video | u"


def test_describe_item_list() -> None:
    req = DownloadRequest(url="u", mode="audio", kind="list", title="My List")
    assert describe_item(req) == "audio | プレイリスト | My List"
