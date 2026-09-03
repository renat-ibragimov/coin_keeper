"""The polite client (app/ukraine_recon/http.py): pause, cache, dead hosts, Wayback."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.ukraine_recon.http import PoliteClient, SourceUnreachableError


class Clock:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def test_cache_serves_the_second_request_without_the_network(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="<html>page</html>", headers={"content-type": "text/html"})

    with PoliteClient(
        cache_dir=tmp_path, transport=httpx.MockTransport(handler), sleep=Clock().sleep
    ) as client:
        first = client.get("https://example.test/a")
        second = client.get("https://example.test/a")
    assert calls == 1
    assert first.text == second.text == "<html>page</html>"
    assert not first.from_cache and second.from_cache
    assert client.cache_hits == 1
    assert any(tmp_path.joinpath("example.test").iterdir())


def test_post_body_is_part_of_the_cache_key(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content.decode())
        return httpx.Response(200, text=request.content.decode())

    with PoliteClient(
        cache_dir=tmp_path, transport=httpx.MockTransport(handler), sleep=Clock().sleep
    ) as client:
        client.post("https://example.test/search", {"page": "1"})
        client.post("https://example.test/search", {"page": "2"})
        client.post("https://example.test/search", {"page": "1"})
    assert seen == ["page=1", "page=2"]


def test_pause_between_requests_to_one_host() -> None:
    clock = Clock()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    with PoliteClient(
        transport=httpx.MockTransport(handler), sleep=clock.sleep, pause_seconds=0.45
    ) as client:
        client.get("https://example.test/1")
        client.get("https://example.test/2")
        client.get("https://other.test/1")
    # One pause for the second request to example.test; none for the first hit on other.test.
    assert len(clock.slept) == 1
    assert 0 < clock.slept[0] <= 0.45


def test_unreachable_host_fails_fast_afterwards() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectTimeout("timed out")

    with PoliteClient(transport=httpx.MockTransport(handler), sleep=Clock().sleep) as client:
        with pytest.raises(SourceUnreachableError):
            client.get("https://dead.test/a")
        with pytest.raises(SourceUnreachableError):
            client.get("https://dead.test/b")
    assert attempts == 1
    assert "dead.test" in client.dead_hosts


def test_read_timeout_is_retried_then_reported() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, text="late but fine")

    with PoliteClient(transport=httpx.MockTransport(handler), sleep=Clock().sleep) as client:
        result = client.get("https://slow.test/a")
    assert result.text == "late but fine"
    assert attempts == 2
    assert not client.dead_hosts


def test_wayback_url_and_timestamp() -> None:
    archived = (
        "https://web.archive.org/web/20260818110850id_/https://www.ua-coins.info/ua/catalog/all/all"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://web.archive.org/web/2026id_/"):
            # The Wayback Machine redirects to the nearest snapshot.
            return httpx.Response(302, headers={"location": archived})
        assert url == archived
        return httpx.Response(200, text="archived")

    with PoliteClient(transport=httpx.MockTransport(handler), sleep=Clock().sleep) as client:
        result = client.get_archived("https://www.ua-coins.info/ua/catalog/all/all")
    assert result.text == "archived"
    assert result.archived_at == "20260818110850"


def test_head_and_range_requests() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(
                200, headers={"content-length": "1234", "content-type": "image/webp"}
            )
        assert request.headers["Range"] == "bytes=0-15"
        return httpx.Response(206, content=b"RIFF....WEBPVP8 ")

    with PoliteClient(transport=httpx.MockTransport(handler), sleep=Clock().sleep) as client:
        head = client.head("https://img.test/a.webp")
        _, body = client.get_range("https://img.test/a.webp", 16)
    assert head.headers["content-length"] == "1234"
    assert body == b"RIFF....WEBPVP8 "
