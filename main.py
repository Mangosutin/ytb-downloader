from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ytbdl import APP_VERSION
from ytbdl.config import Config, load_config
from ytbdl.cli import resolve_url
from ytbdl.core import (
    _archive_contains,
    _resolve_playlist_item_selection,
    _video_id_from_url,
    download,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="YTB downloader",
        description="YouTube動画・音声ダウンローダー",
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="ダウンロードするYouTube URL",
    )
    parser.add_argument(
        "--mode",
        choices=("video", "audio"),
        default=None,
        help="ダウンロードモード",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="設定ファイルのパス",
    )
    parser.add_argument(
        "--linklist",
        type=Path,
        default=None,
        help="JSON形式のリンクリスト",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"YTB downloader {APP_VERSION}",
    )
    return parser


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"ytbdl_{timestamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )


def load_linklist(path: Path) -> list[dict[str, str | None]]:
    """JSON リンクリストを読み込む。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"リンクリストの読み込みに失敗しました: {path}: {exc}"
        ) from exc
    if not isinstance(data, list):
        raise ValueError("リンクリストは配列で指定してください")
    result: list[dict[str, str | None]] = []
    for index, item in enumerate(data, start=1):
        if isinstance(item, str):
            if not item:
                raise ValueError(
                    f"リンクリスト {index} 件目の URL が空です"
                )
            result.append({"url": item, "mode": None})
            continue
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("url"), str)
            or not item.get("url")
        ):
            raise ValueError(
                f"リンクリスト {index} 件目に url がありません"
            )
        mode = item.get("mode")
        if mode is not None and mode not in ("audio", "video"):
            raise ValueError(
                f"リンクリスト {index} 件目の mode が不正です: {mode}"
            )
        result.append({"url": item["url"], "mode": mode})
    return result


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.url and not args.linklist:
        parser.error("URLまたは --linklist を指定してください。")
    if args.url and args.linklist:
        parser.error("URLと --linklist は同時に指定できません。")

    app_dir = Path(__file__).resolve().parent
    try:
        config = load_config(
            args.config or app_dir / "config.toml",
            app_dir=app_dir,
        )
        setup_logging(config.log_dir)
        default_mode = args.mode or config.default_mode
        if default_mode not in ("video", "audio"):
            raise ValueError(f"不正なモードです:{default_mode}")

        logger = logging.getLogger(__name__)
        logger.info(
            "YTB downloader v%s started. mode=%s",
            APP_VERSION,
            default_mode,
        )

        if args.linklist:
            items = load_linklist(args.linklist)
            success = skipped = failed = 0
            for item in items:
                url = resolve_url(item["url"])
                mode = item["mode"] or default_mode
                try:
                    if mode not in ("video", "audio"):
                        raise ValueError(f"不正なモードです:{mode}")
                    playlist_item, effective_url = (
                        _resolve_playlist_item_selection(url)
                    )
                    video_id = _video_id_from_url(effective_url)
                    if _archive_contains(config, video_id):
                        logger.info(
                            "アーカイブ済みのためスキップします: %s",
                            effective_url,
                        )
                        skipped += 1
                        continue
                    download(url, mode, config)
                    success += 1
                except Exception:
                    failed += 1
                    logger.exception(
                        "リンクリストの処理に失敗しました: %s",
                        url,
                    )
            logger.info(
                "リンクリスト処理結果: 成功=%d, スキップ=%d, 失敗=%d",
                success,
                skipped,
                failed,
            )
            return 1 if failed else 0

        url = resolve_url(args.url)
        if not url:
            parser.error("URLを指定してください。")
        mode = default_mode
        download(url, mode, config)
        logger.info("処理が終了しました。")
        return 0
    except Exception:
        logging.getLogger(__name__).exception("処理中にエラーが発生しました。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
