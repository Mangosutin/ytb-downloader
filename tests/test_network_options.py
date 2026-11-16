from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

# Keep the option-building tests runnable without the runtime dependency.
# Actual download execution still requires the yt-dlp package.
if importlib.util.find_spec("yt_dlp") is None:
    yt_dlp_stub = ModuleType("yt_dlp")
    yt_dlp_stub.version = SimpleNamespace(__version__="test-stub")  # type: ignore[attr-defined]
    yt_dlp_stub.YoutubeDL = object  # type: ignore[attr-defined]
    sys.modules["yt_dlp"] = yt_dlp_stub

from ytbdl import core
from ytbdl.config import load_config


def _run_download_with_fake_yt_dlp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    fail_with: Exception | None = None,
) -> list[dict[str, Any]]:
    captured_options: list[dict[str, Any]] = []

    class FakeYoutubeDL:
        def __init__(self, options: dict[str, Any]) -> None:
            captured_options.append(options)

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: Any) -> bool:
            return False

        def extract_info(self, url: str, download: bool = False) -> dict[str, str]:
            assert url == "https://example.test/video"
            assert download is False
            return {"id": "abc123", "title": "Test video"}

        def process_ie_result(
            self, info: dict[str, Any], download: bool = False
        ) -> dict[str, Any]:
            assert download is True
            if fail_with is not None:
                raise fail_with
            return info

    monkeypatch.setattr(core.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    config = load_config(tmp_path / "missing.toml", app_dir=tmp_path)
    core.download("https://example.test/video", "audio", config)
    return captured_options


def test_force_ipv4_is_enabled_by_default(tmp_path: Path) -> None:
    config = load_config(tmp_path / "missing.toml", app_dir=tmp_path)

    assert config.force_ipv4 is True


def test_force_ipv4_can_be_disabled(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("force_ipv4 = false\n", encoding="utf-8")
    config = load_config(config_file, app_dir=tmp_path)

    assert config.force_ipv4 is False


def test_download_uses_ipv4_for_metadata_and_media(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    options = _run_download_with_fake_yt_dlp(monkeypatch, tmp_path)

    assert len(options) == 2
    assert all(item["source_address"] == "0.0.0.0" for item in options)


def test_download_can_disable_ipv4(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("force_ipv4 = false\n", encoding="utf-8")
    captured_options: list[dict[str, Any]] = []

    class FakeYoutubeDL:
        def __init__(self, options: dict[str, Any]) -> None:
            captured_options.append(options)

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: Any) -> bool:
            return False

        def extract_info(self, url: str, download: bool = False) -> dict[str, str]:
            return {"id": "abc123", "title": "Test video"}

        def process_ie_result(
            self, info: dict[str, Any], download: bool = False
        ) -> dict[str, Any]:
            return info

    monkeypatch.setattr(core.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    config = load_config(config_file, app_dir=tmp_path)
    core.download("https://example.test/video", "audio", config)

    assert len(captured_options) == 2
    assert all("source_address" not in item for item in captured_options)


def test_http_403_logs_ipv4_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    class FakeYoutubeDL:
        def __init__(self, options: dict[str, Any]) -> None:
            pass

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: Any) -> bool:
            return False

        def extract_info(self, url: str, download: bool = False) -> dict[str, str]:
            return {"id": "abc123", "title": "Test video"}

        def process_ie_result(
            self, info: dict[str, Any], download: bool = False
        ) -> dict[str, Any]:
            raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(core.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    config = load_config(tmp_path / "missing.toml", app_dir=tmp_path)

    with pytest.raises(RuntimeError, match="HTTP Error 403"):
        core.download("https://example.test/video", "audio", config)

    assert "IPv4固定は有効です" in caplog.text
