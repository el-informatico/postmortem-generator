"""Shared exceptions for piece 1 (collector)."""
from __future__ import annotations


class CollectorError(Exception):
    """Base class for every error raised by the evidence collector."""


class OfflineCacheMiss(CollectorError):
    """offline=True was requested but the URL is not in the disk cache.

    Attributes:
        url: the API URL that was not cached.
    """

    def __init__(self, url: str, message: str | None = None) -> None:
        self.url = url
        super().__init__(
            message
            or (
                f"offline cache miss for {url} — the GitHub response is not "
                f"cached; run scripts/refresh_cache.py first (or collect with "
                f"offline=False)"
            )
        )
