from __future__ import annotations

import os
from collections.abc import Mapping


def resolve_url(
    cli_url: str | None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve a URL from the CLI or launcher-provided environment."""
    if cli_url:
        return cli_url
    environment = os.environ if env is None else env
    return environment.get("YTB_DOWNLOADER_URL") or None
