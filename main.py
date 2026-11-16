from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ytbdl import APP_VERSION
from ytbdl.config import Config, load_config
from ytbdl.cli import resolve_url
from ytbdl.core import download


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


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    url = resolve_url(args.url)
    if not url:
        parser.error("URLを指定してください。")
    app_dir = Path(__file__).resolve().parent
    try:
        config = load_config(
            args.config or app_dir / "config.toml",
            app_dir=app_dir,
        )
        setup_logging(config.log_dir)
        mode = args.mode or config.default_mode
        if mode not in ("video", "audio"):
            raise ValueError(f"不正なモードです:{mode}")
        logging.getLogger(__name__).info(
            "YTB downloader v%s started. mode=%s",
            APP_VERSION,
            mode,
        )
        download(url, mode, config)
        logging.getLogger(__name__).info("処理が終了しました。")
        return 0
    except Exception:
        logging.getLogger(__name__).exception("処理中にエラーが発生しました。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
