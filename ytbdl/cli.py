from __future__ import annotations

import os


def resolve_url(cli_url: str | None, env: dict[str, str] | None = None) -> str | None:
    """CLI の URL があれば優先し、無ければ環境変数を返す。"""
    if cli_url:
        return cli_url
    source = os.environ if env is None else env
    value = source.get("YTB_DOWNLOADER_URL")
    return value or None
