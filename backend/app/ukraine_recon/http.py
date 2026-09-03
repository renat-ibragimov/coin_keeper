"""A polite HTTP client: honest User-Agent, a pause per host, a disk cache.

Repeated runs must not hit the sites again: every response is cached on disk
under --cache-dir, keyed by method, URL and body. A host that refuses the
connection is remembered as dead for the rest of the run so the script fails
fast instead of waiting out a timeout per URL.

The Wayback Machine is a fallback for ua-coins.info only: the site does not
answer from outside Ukraine (see docs/05-integrations.md, reconnaissance).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger("app.ukraine_recon.http")

USER_AGENT = "CoinKeeper/0.1 personal collection (recon; https://coins.renat-ibragimov.com)"
DEFAULT_PAUSE_SECONDS = 0.45
DEFAULT_TIMEOUT_SECONDS = 20.0
# The Wayback Machine serves megabyte pages slowly; it gets a longer read timeout.
WAYBACK_TIMEOUT_SECONDS = 90.0
READ_RETRIES = 3
WAYBACK_PREFIX = "https://web.archive.org/web/"
# `id_` asks for the archived bytes without the Wayback toolbar injected.
WAYBACK_NEAREST = "2026"


class SourceUnreachableError(Exception):
    """The host does not answer at the network level."""

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(f"{host}: {reason}")
        self.host = host
        self.reason = reason


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    final_url: str
    headers: dict[str, str] = field(default_factory=dict)
    from_cache: bool = False
    archived_at: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class PoliteClient:
    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        user_agent: str = USER_AGENT,
        pause_seconds: float = DEFAULT_PAUSE_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        sleep: object = time.sleep,
    ) -> None:
        self.cache_dir = cache_dir
        self.pause_seconds = pause_seconds
        self._sleep = sleep
        self._last_request_at: dict[str, float] = {}
        self.dead_hosts: dict[str, str] = {}
        self.requests_made = 0
        self.cache_hits = 0
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "uk,en;q=0.8"},
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------ public API
    def get(self, url: str) -> FetchResult:
        return self._request("GET", url, None)

    def post(self, url: str, data: dict[str, str]) -> FetchResult:
        return self._request("POST", url, data)

    def head(self, url: str) -> FetchResult:
        return self._request("HEAD", url, None)

    def get_range(self, url: str, max_bytes: int) -> tuple[FetchResult, bytes]:
        """The first bytes of a file: enough to read image dimensions."""
        cached = self._read_cache("RANGE", url, str(max_bytes))
        if cached is not None:
            return cached, bytes.fromhex(cached.text)
        response = self._send("GET", url, None, headers={"Range": f"bytes=0-{max_bytes - 1}"})
        body = response.content[:max_bytes]
        result = FetchResult(
            url=url,
            status=response.status_code,
            text=body.hex(),
            final_url=str(response.url),
            headers=_interesting_headers(response),
        )
        self._write_cache("RANGE", url, str(max_bytes), result)
        return result, body

    def get_archived(self, url: str, *, nearest: str = WAYBACK_NEAREST) -> FetchResult:
        """The Wayback Machine copy of `url` closest to `nearest` (a timestamp prefix)."""
        archive_url = f"{WAYBACK_PREFIX}{nearest}id_/{url}"
        result = self._request("GET", archive_url, None)
        result.archived_at = _archived_timestamp(result.final_url)
        return result

    # --------------------------------------------------------------- internals
    def _request(self, method: str, url: str, data: dict[str, str] | None) -> FetchResult:
        body = json.dumps(data, sort_keys=True, ensure_ascii=False) if data else ""
        cached = self._read_cache(method, url, body)
        if cached is not None:
            return cached
        response = self._send(method, url, data)
        result = FetchResult(
            url=url,
            status=response.status_code,
            text="" if method == "HEAD" else response.text,
            final_url=str(response.url),
            headers=_interesting_headers(response),
        )
        self._write_cache(method, url, body, result)
        return result

    def _send(
        self,
        method: str,
        url: str,
        data: dict[str, str] | None,
        *,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        host = urlsplit(url).hostname or url
        if host in self.dead_hosts:
            raise SourceUnreachableError(host, self.dead_hosts[host])
        timeout = (
            WAYBACK_TIMEOUT_SECONDS if url.startswith(WAYBACK_PREFIX) else httpx.USE_CLIENT_DEFAULT
        )
        for attempt in range(1, READ_RETRIES + 1):
            self._wait_for_host(host)
            try:
                response = self._client.request(
                    method, url, data=data, headers=headers, timeout=timeout
                )
                break
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                reason = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                self.dead_hosts[host] = reason
                logger.warning("host marked unreachable: %s (%s)", host, reason)
                raise SourceUnreachableError(host, reason) from exc
            except (httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError) as exc:
                # The host answers but slowly or drops the connection: retry
                # with a longer pause, do not write it off.
                reason = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                logger.warning("%s %s attempt %d: %s", method, url, attempt, reason)
                if attempt == READ_RETRIES:
                    raise SourceUnreachableError(host, reason) from exc
                self._sleep(self.pause_seconds * 4 * attempt)  # type: ignore[operator]
            finally:
                self._last_request_at[host] = time.monotonic()
                self.requests_made += 1
        if response.status_code >= 500:
            # One retry after a longer pause; the sites are small and a 5xx
            # is usually a hiccup rather than a ban.
            self._sleep(self.pause_seconds * 4)  # type: ignore[operator]
            self._last_request_at[host] = time.monotonic()
            self.requests_made += 1
            response = self._client.request(
                method, url, data=data, headers=headers, timeout=timeout
            )
        return response

    def _wait_for_host(self, host: str) -> None:
        last = self._last_request_at.get(host)
        if last is None:
            return
        remaining = self.pause_seconds - (time.monotonic() - last)
        if remaining > 0:
            self._sleep(remaining)  # type: ignore[operator]

    def _cache_path(self, method: str, url: str, body: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(f"{method}\n{url}\n{body}".encode()).hexdigest()
        host = urlsplit(url).hostname or "unknown"
        return self.cache_dir / host / f"{digest}.json"

    def _read_cache(self, method: str, url: str, body: str) -> FetchResult | None:
        path = self._cache_path(method, url, body)
        if path is None or not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.cache_hits += 1
        return FetchResult(
            url=url,
            status=int(payload["status"]),
            text=str(payload["text"]),
            final_url=str(payload["finalUrl"]),
            headers=dict(payload.get("headers", {})),
            from_cache=True,
        )

    def _write_cache(self, method: str, url: str, body: str, result: FetchResult) -> None:
        path = self._cache_path(method, url, body)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "method": method,
            "url": url,
            "body": body,
            "status": result.status,
            "finalUrl": result.final_url,
            "headers": result.headers,
            "text": result.text,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _interesting_headers(response: httpx.Response) -> dict[str, str]:
    keep = ("content-type", "content-length", "last-modified", "x-archive-orig-date")
    return {name: response.headers[name] for name in keep if name in response.headers}


def _archived_timestamp(final_url: str) -> str | None:
    if not final_url.startswith(WAYBACK_PREFIX):
        return None
    rest = final_url[len(WAYBACK_PREFIX) :]
    stamp = rest.split("/", 1)[0].removesuffix("id_")
    return stamp if stamp.isdigit() else None
