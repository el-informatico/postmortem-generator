"""GitHub REST API client with a sha256-keyed on-disk cache (piece 1).

Stdlib only: ``urllib.request`` for HTTP, ``json``/``hashlib``/``pathlib``
for the cache. The single network seam is ``GitHubClient._fetch`` so unit
tests can monkeypatch it with canned responses — no test ever touches the
network.

Cache file layout: ``<cache_dir>/<sha256(url)>.json`` containing
``{"url": ..., "fetched_at": ..., "status": 200, "body": <parsed json>,
"next_url": <Link rel="next" or "">}``. The extra ``next_url`` key lets an
offline client follow the same pagination path the online client took.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pmg.collector.errors import CollectorError, OfflineCacheMiss
from pmg.contracts import CaseConfig

BASE_URL = "https://api.github.com"
MAX_PAGES = 10  # hard cap for automatic Link-header pagination

_LINK_NEXT_RE = re.compile(r'<([^>]*)>\s*;\s*rel="next"', re.IGNORECASE)


class GitHubAPIError(CollectorError):
    """A GitHub API request failed (non-200 or transport error)."""

    def __init__(self, status: int, url: str, body: str) -> None:
        self.status = status
        self.url = url
        self.body = body
        super().__init__(f"GitHub API error {status} for {url}: {body[:500]}")


class GitHubClient:
    """Minimal read-only GitHub REST client with disk cache and pagination."""

    def __init__(
        self,
        repo: str,
        token: str | None = None,
        cache_dir: Path | None = None,
        offline: bool = False,
    ) -> None:
        """``token`` falls back to the GITHUB_TOKEN environment variable.

        ``offline=True`` never touches the network: reads only from
        ``cache_dir`` and raises :class:`OfflineCacheMiss` on a miss.
        """
        self.repo = repo
        self.token = token or os.environ.get("GITHUB_TOKEN") or None
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.offline = offline
        # every API URL accessed through this client, in order (deduped by
        # the caller's usage pattern); warm_cache() reports these.
        self.fetched_urls: list[str] = []

    # -- HTTP seam (monkeypatch me in tests) -------------------------------
    def _fetch(self, url: str, headers: dict[str, str]) -> tuple[int, Any, dict[str, str]]:
        """Perform one HTTP GET; return ``(status, parsed_body, headers)``.

        Raises :class:`GitHubAPIError` on HTTP errors and transport errors.
        This is the only method that touches the network.
        """
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8", "replace")
                response_headers: dict[str, str] = {}
                link = response.headers.get("Link")
                if link:
                    response_headers["Link"] = link
                return response.status, json.loads(raw), response_headers
        except urllib.error.HTTPError as exc:  # non-2xx
            body = exc.read().decode("utf-8", "replace")
            raise GitHubAPIError(exc.code, url, body[:500]) from None
        except urllib.error.URLError as exc:  # DNS, timeout, refused, ...
            raise GitHubAPIError(0, url, str(exc.reason)) from None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "postmortem-generator",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    # -- cache --------------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        assert self.cache_dir is not None
        return self.cache_dir / f"{key}.json"

    def _cache_write(self, url: str, body: Any, next_url: str) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "url": url,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": 200,
            "body": body,
            "next_url": next_url,
        }
        self._cache_path(url).write_text(
            json.dumps(entry, indent=2) + "\n", encoding="utf-8"
        )

    def _cache_read(self, url: str) -> Any:
        """Read one URL's cached body; raise OfflineCacheMiss when absent."""
        if self.cache_dir is None:
            raise OfflineCacheMiss(url)
        path = self._cache_path(url)
        if not path.exists():
            raise OfflineCacheMiss(url)
        entry = json.loads(path.read_text(encoding="utf-8"))
        return entry.get("body")

    def _cache_read_next_url(self, url: str) -> str:
        if self.cache_dir is None:
            return ""
        path = self._cache_path(url)
        if not path.exists():
            return ""
        entry = json.loads(path.read_text(encoding="utf-8"))
        return entry.get("next_url") or ""

    # -- public API ---------------------------------------------------------
    def get_json(self, path: str) -> Any:
        """GET ``path`` (e.g. ``/repos/curl/curl/issues/4907`` or with a
        ``?query``) and return the parsed JSON.

        Online: fetch, cache, and automatically follow ``Link rel="next"``
        for list responses (up to :data:`MAX_PAGES` pages, merged in order).
        Offline: read from cache only, following the same recorded pagination
        chain; any missing page raises :class:`OfflineCacheMiss`.
        """
        url = BASE_URL + path
        self.fetched_urls.append(url)
        if self.offline:
            body = self._cache_read(url)
            next_url = self._cache_read_next_url(url)
            pages = 1
            while (
                isinstance(body, list)
                and next_url
                and pages < MAX_PAGES
            ):
                self.fetched_urls.append(next_url)
                page = self._cache_read(next_url)
                if not isinstance(page, list):
                    break
                body.extend(page)
                next_url = self._cache_read_next_url(next_url)
                pages += 1
            return body

        status, body, response_headers = self._fetch(url, self._headers())
        if status != 200:  # defensive; _fetch already raises on HTTP errors
            raise GitHubAPIError(status, url, str(body)[:500])
        next_url = _LINK_NEXT_RE.search(response_headers.get("Link", ""))
        next_url = next_url.group(1) if next_url else ""
        self._cache_write(url, body, next_url)
        pages = 1
        while isinstance(body, list) and next_url and pages < MAX_PAGES:
            self.fetched_urls.append(next_url)
            status, page, response_headers = self._fetch(next_url, self._headers())
            if status != 200:
                raise GitHubAPIError(status, next_url, str(page)[:500])
            link = _LINK_NEXT_RE.search(response_headers.get("Link", ""))
            link_url = link.group(1) if link else ""
            self._cache_write(next_url, page, link_url)
            if not isinstance(page, list):
                break
            body.extend(page)
            next_url = link_url
            pages += 1
        return body

    def issue(self, n: int) -> dict[str, Any]:
        """Fetch issue/PR ``n`` metadata."""
        result = self.get_json(f"/repos/{self.repo}/issues/{n}")
        return result if isinstance(result, dict) else {}

    def issue_comments(self, n: int) -> list[dict[str, Any]]:
        """Fetch all comments of issue ``n`` (paginated, merged in order)."""
        result = self.get_json(f"/repos/{self.repo}/issues/{n}/comments?per_page=100")
        return result if isinstance(result, list) else []


def warm_cache(case: CaseConfig, cache_dir: Path) -> list[str]:
    """Prefetch (online) the GitHub data a case needs: each issue and its
    comments. Returns the list of API URLs fetched; used by
    ``scripts/refresh_cache.py``."""
    client = GitHubClient(case.repo, cache_dir=cache_dir, offline=False)
    for n in case.issues:
        client.issue(n)
        client.issue_comments(n)
    return client.fetched_urls
