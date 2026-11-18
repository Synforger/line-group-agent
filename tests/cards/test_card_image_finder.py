"""The card image finder over a fake web: pages are served by a mock transport and names are
resolved by a table, so no test touches a network."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from line_group_agent.cards.card import Card
from line_group_agent.cards.card_image_finder import MAX_REDIRECTS, CardImageFinder

pytestmark = pytest.mark.anyio

PUBLIC_IP = "93.184.216.34"
OG_PAGE = (
    '<html><head><meta property="og:image" content="https://cdn.example.com/{name}.jpg">'
    "</head><body>x</body></html>"
)
Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def card(name: str = "a", **changes: Any) -> Card:
    fields: dict[str, Any] = {"title": name, "text": "x", "url": f"https://{name}.example.com/p"}
    fields.update(changes)
    return Card(**fields)


class Web:
    """A fake web: `serve` answers a request, `names` maps a host name to its addresses
    (a name not in the table resolves to a public address), `requests` keeps what came."""

    def __init__(self, serve: Handler, names: dict[str, list[str]] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.resolved: list[str] = []
        self._serve = serve
        self._names = names or {}

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self._serve(request)
        return await response if isinstance(response, Awaitable) else response

    async def resolve(self, host: str) -> list[str]:
        self.resolved.append(host)
        if host not in self._names:
            return [PUBLIC_IP]
        if isinstance(self._names[host], OSError):
            raise self._names[host]  # type: ignore[misc]
        return self._names[host]

    def finder(self, **options: Any) -> CardImageFinder:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        return CardImageFinder(http_client=client, resolver=self.resolve, **options)


def page_of(content: str, content_type: str = "text/html; charset=utf-8") -> httpx.Response:
    return httpx.Response(200, content=content.encode(), headers={"content-type": content_type})


def og_page(request: httpx.Request) -> httpx.Response:
    return page_of(OG_PAGE.format(name=request.headers["host"].split(".")[0]))


async def test_a_card_without_a_picture_gets_the_og_image_of_its_page() -> None:
    web = Web(og_page)
    [filled] = await web.finder().fill([card("gion")])
    assert filled.image_url == "https://cdn.example.com/gion.jpg"
    assert (filled.title, filled.url) == ("gion", "https://gion.example.com/p")


async def test_the_connection_goes_to_the_checked_address_under_the_cards_name() -> None:
    web = Web(og_page)
    await web.finder().fill([card("gion")])
    [request] = web.requests
    assert request.url.host == PUBLIC_IP and request.url.scheme == "https"
    assert request.headers["host"] == "gion.example.com"
    assert request.extensions["sni_hostname"] == "gion.example.com"
    assert web.resolved == ["gion.example.com"]


async def test_an_ipv6_address_is_pinned_in_brackets() -> None:
    web = Web(og_page, {"gion.example.com": ["2606:2800:220:1:248:1893:25c8:1946"]})
    [filled] = await web.finder().fill([card("gion")])
    assert filled.image_url is not None
    assert web.requests[0].url.host == "2606:2800:220:1:248:1893:25c8:1946"


async def test_the_twitter_image_is_the_second_choice() -> None:
    web = Web(
        lambda request: page_of(
            '<meta name="twitter:image" content="https://cdn.example.com/t.jpg">'
        )
    )
    [filled] = await web.finder().fill([card()])
    assert filled.image_url == "https://cdn.example.com/t.jpg"


async def test_a_card_that_has_a_picture_is_left_alone_and_its_page_is_not_read() -> None:
    web = Web(og_page)
    own = card("own", image_url="https://example.com/own.jpg")
    filled = await web.finder().fill([own])
    assert filled == [own] and web.requests == [] and web.resolved == []


async def test_only_the_cards_without_a_picture_are_looked_up_and_the_order_is_kept() -> None:
    web = Web(og_page)
    own = card("own", image_url="https://example.com/own.jpg")
    filled = await web.finder().fill([card("a"), own, card("b")])
    assert [c.image_url for c in filled] == [
        "https://cdn.example.com/a.jpg",
        "https://example.com/own.jpg",
        "https://cdn.example.com/b.jpg",
    ]
    assert len(web.requests) == 2


async def test_a_page_without_a_picture_leaves_the_card_as_it_was() -> None:
    web = Web(lambda request: page_of("<html><head></head></html>"))
    original = card()
    assert await web.finder().fill([original]) == [original]


async def test_a_picture_address_that_is_not_https_is_not_taken() -> None:
    web = Web(
        lambda request: page_of('<meta property="og:image" content="http://x.example.com/a.jpg">')
    )
    original = card()
    assert await web.finder().fill([original]) == [original]


@pytest.mark.parametrize("status", [404, 403, 500])
async def test_a_page_that_does_not_open_gives_nothing(status: int) -> None:
    web = Web(lambda request: httpx.Response(status, content=b"x"))
    original = card()
    assert await web.finder().fill([original]) == [original]


async def test_a_page_that_is_not_html_is_not_read() -> None:
    web = Web(lambda request: page_of(OG_PAGE.format(name="a"), "application/pdf"))
    original = card()
    assert await web.finder().fill([original]) == [original]


async def test_a_page_that_gives_no_content_type_is_read() -> None:
    web = Web(lambda request: httpx.Response(200, content=OG_PAGE.format(name="a").encode()))
    [filled] = await web.finder().fill([card()])
    assert filled.image_url == "https://cdn.example.com/a.jpg"


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.1.2.3"],
        ["192.168.0.10"],
        ["169.254.169.254"],
        ["::1"],
        ["fd00::5"],
        ["::ffff:127.0.0.1"],
        [PUBLIC_IP, "10.0.0.1"],
        [],
    ],
)
async def test_a_name_that_resolves_to_an_inside_address_is_never_connected_to(
    addresses: list[str],
) -> None:
    web = Web(og_page, {"a.example.com": addresses})
    original = card()
    assert await web.finder().fill([original]) == [original]
    assert web.requests == []


async def test_an_address_written_as_an_ip_is_judged_the_same_way() -> None:
    # A system resolver answers an IP written as a host with that same IP.
    web = Web(og_page, {"127.0.0.1": ["127.0.0.1"], PUBLIC_IP: [PUBLIC_IP]})
    inside = card("inside", url="https://127.0.0.1/admin")
    outside = card("outside", url=f"https://{PUBLIC_IP}/p")
    filled = await web.finder().fill([inside, outside])
    assert filled[0].image_url is None
    assert filled[1].image_url is not None
    assert [request.url.host for request in web.requests] == [PUBLIC_IP]


async def test_a_name_that_does_not_resolve_gives_nothing() -> None:
    web = Web(og_page, {"a.example.com": OSError("no such host")})  # type: ignore[dict-item]
    original = card()
    assert await web.finder().fill([original]) == [original]
    assert web.requests == []


@pytest.mark.parametrize(
    "url",
    ["https://a.example.com:8443/p", "https://user:pw@a.example.com/p", "http://a.example.com/p"],
)
async def test_only_https_on_the_default_port_without_credentials_is_fetched(url: str) -> None:
    web = Web(og_page)
    original = card(url=url)
    assert await web.finder().fill([original]) == [original]
    assert web.requests == []


async def test_a_redirect_is_followed_and_its_target_is_checked_too() -> None:
    def serve(request: httpx.Request) -> httpx.Response:
        if request.headers["host"] == "a.example.com":
            return httpx.Response(301, headers={"location": "https://www.a.example.com/new"})
        return page_of(OG_PAGE.format(name="moved"))

    web = Web(serve)
    [filled] = await web.finder().fill([card()])
    assert filled.image_url == "https://cdn.example.com/moved.jpg"
    assert [r.headers["host"] for r in web.requests] == ["a.example.com", "www.a.example.com"]


async def test_a_relative_redirect_stays_on_the_same_name() -> None:
    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/p":
            return httpx.Response(302, headers={"location": "/other"})
        return page_of(OG_PAGE.format(name="rel"))

    web = Web(serve)
    [filled] = await web.finder().fill([card()])
    assert filled.image_url == "https://cdn.example.com/rel.jpg"
    assert [r.url.path for r in web.requests] == ["/p", "/other"]


@pytest.mark.parametrize(
    "location",
    ["http://a.example.com/new", "https://inside.example.com/", "https://a.example.com:8080/x"],
)
async def test_a_redirect_to_http_an_inside_address_or_another_port_is_not_followed(
    location: str,
) -> None:
    web = Web(
        lambda request: httpx.Response(302, headers={"location": location}),
        {"inside.example.com": ["10.0.0.9"]},
    )
    original = card()
    assert await web.finder().fill([original]) == [original]
    assert len(web.requests) == 1


async def test_a_chain_of_redirects_is_cut_after_a_few() -> None:
    web = Web(lambda request: httpx.Response(302, headers={"location": "/again"}))
    original = card()
    assert await web.finder().fill([original]) == [original]
    assert len(web.requests) == MAX_REDIRECTS + 1


async def test_a_slow_page_is_given_up_after_the_time_limit() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return og_page(request)

    web = Web(slow)
    original = card()
    started = asyncio.get_running_loop().time()
    assert await web.finder(timeout_seconds=0.05).fill([original]) == [original]
    assert asyncio.get_running_loop().time() - started < 1


async def test_only_the_start_of_a_page_is_read() -> None:
    late = "<p>" + "x" * 5000 + "</p>" + OG_PAGE.format(name="late")
    early = OG_PAGE.format(name="early") + "<p>" + "x" * 5000 + "</p>"
    web = Web(
        lambda request: page_of(late if request.headers["host"] == "late.example.com" else early)
    )
    filled = await web.finder(max_page_bytes=1000).fill([card("late"), card("early")])
    assert [c.image_url for c in filled] == [None, "https://cdn.example.com/early.jpg"]


async def test_the_pages_are_fetched_side_by_side() -> None:
    arrived: list[str] = []
    both_arrived = asyncio.Event()

    async def serve(request: httpx.Request) -> httpx.Response:
        arrived.append(request.headers["host"])
        if len(arrived) == 2:
            both_arrived.set()
        # One page waits for the other to be asked: read one after the other, this times out.
        await asyncio.wait_for(both_arrived.wait(), timeout=1)
        return og_page(request)

    web = Web(serve)
    filled = await web.finder(timeout_seconds=2).fill([card("a"), card("b")])
    assert [c.image_url for c in filled] == [
        "https://cdn.example.com/a.jpg",
        "https://cdn.example.com/b.jpg",
    ]


async def test_one_card_that_fails_does_not_stop_the_others() -> None:
    def serve(request: httpx.Request) -> httpx.Response:
        if request.headers["host"] == "bad.example.com":
            raise httpx.ConnectError("refused")
        return og_page(request)

    web = Web(serve)
    filled = await web.finder().fill([card("bad"), card("good")])
    assert [c.image_url for c in filled] == [None, "https://cdn.example.com/good.jpg"]


async def test_no_cards_means_no_lookups() -> None:
    web = Web(og_page)
    assert await web.finder().fill([]) == []
    assert web.requests == []
