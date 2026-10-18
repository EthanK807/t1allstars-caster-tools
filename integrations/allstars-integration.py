"""Client for the Tyler1 All-Stars public data API.

Docs: https://t1allstars.com/data

The API is unauthenticated. Responses use ``Cache-Control: no-store``, and the
feed reports a suggested poll interval (currently 5 seconds). Timestamps are
ISO 8601 in UTC.

Resource methods belong on :class:`AllStarsClient` as you decide which data
the predictor needs. Paths for the documented endpoints are on :class:`Endpoints`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from typing import Any

DEFAULT_BASE_URL = "https://t1allstars.com"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
USER_AGENT = "t1allstars-champion-predictor/0.1"


class Endpoints:
    """Paths from https://t1allstars.com/data."""

    FEED = "/api/feed.json"
    BROADCAST_STATS = "/api/broadcast/stats"
    BROADCAST_SUMMARY = "/api/broadcast/summary"
    LIVE_MATCHES = "/api/matches/live"
    TOURNAMENTS = "/api/public/tournaments"
    STANDINGS = "/api/public/standings"
    PLAYERS = "/api/public/players"
    MATCHES = "/api/public/matches"

    @staticmethod
    def tournament(week: int) -> str:
        return f"/api/public/tournaments/{week}"

    @staticmethod
    def pickems(week: int) -> str:
        return f"/api/broadcast/pickems/{week}"


class AllStarsApiError(Exception):
    """A public API request failed."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class AllStarsClient:
    """Fetch and poll JSON from the Tyler1 All-Stars public API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET ``path`` and return the decoded JSON body.

        ``path`` is relative to the API origin, for example
        :attr:`Endpoints.FEED`. ``params`` are encoded as a query string;
        ``None`` values are omitted.
        """
        url = self._url(path, params)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            message = f"HTTP {exc.code} for {url}"
            if detail:
                message = f"{message}: {detail[:500]}"
            raise AllStarsApiError(message, status=exc.code, url=url) from exc
        except urllib.error.URLError as exc:
            raise AllStarsApiError(f"Request failed for {url}: {exc.reason}", url=url) from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise AllStarsApiError(f"Response from {url} was not JSON", url=url) from exc

    def poll(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        interval: float | None = None,
        on_error: Callable[[AllStarsApiError], None] | None = None,
    ) -> Iterator[Any]:
        """Yield each successful JSON response until the caller stops iterating.

        Sleeps ``interval`` seconds between attempts. When omitted, uses
        :attr:`poll_interval`. If ``on_error`` is set, request failures are
        passed to it and polling continues. Otherwise the error is raised.
        """
        wait = self.poll_interval if interval is None else interval
        if wait < 0:
            raise ValueError("interval must be >= 0")

        while True:
            try:
                yield self.get(path, params)
            except AllStarsApiError as exc:
                if on_error is None:
                    raise
                on_error(exc)
            if wait:
                time.sleep(wait)

    def _url(self, path: str, params: Mapping[str, Any] | None) -> str:
        if path.startswith(("http://", "https://")):
            url = path
        else:
            url = f"{self.base_url}/{path.lstrip('/')}"
        if not params:
            return url
        query = urllib.parse.urlencode(
            {key: value for key, value in params.items() if value is not None}
        )
        if not query:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{query}"
