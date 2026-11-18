"""Give a card that came without a picture the picture its own page names.

Web search results seldom carry an image address, so the model's cards mostly have none. For
each such card the finder reads the start of the card's page and takes its `og:image` (else
`twitter:image`). Every step is held to a small, safe shape: `https` only, the default port,
a public address only (checked on the addresses the name resolves to, and the connection is
made to the address that was checked, so the name cannot change its answer in between), at
most a few redirects each checked the same way, two seconds for a page, and only the first
bytes of it. Anything that goes wrong leaves the card without a picture. Called by the
answerer; the pages are fetched side by side.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from line_group_agent.cards.card import Card
from line_group_agent.cards.card_input import usable_https_url
from line_group_agent.cards.page_image_parser import find_page_image
from line_group_agent.cards.public_address import is_public_address

logger = logging.getLogger(__name__)

PAGE_TIMEOUT_SECONDS = 2.0
MAX_PAGE_BYTES = 256 * 1024
MAX_REDIRECTS = 3
HTTPS_PORT = 443
HTTP_OK = 200
USER_AGENT = "line-group-agent (link preview)"
HTML_MARKER = "html"

Resolver = Callable[[str], Awaitable[list[str]]]


class CardImageFinder:
    """Finds the pictures of cards from their pages."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        resolver: Resolver | None = None,
        timeout_seconds: float = PAGE_TIMEOUT_SECONDS,
        max_page_bytes: int = MAX_PAGE_BYTES,
    ) -> None:
        # trust_env=False: no proxy or certificate settings from environment variables.
        # No kept-alive connections: a connection is made to a checked IP address, and one
        # kept for a name must not be reused for another name that shares the address.
        self._http = http_client or httpx.AsyncClient(
            timeout=timeout_seconds,
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        self._resolve = resolver or _resolve_with_system
        self._timeout_seconds = timeout_seconds
        self._max_page_bytes = max_page_bytes

    async def fill(self, cards: Sequence[Card]) -> list[Card]:
        """Return the cards, each one that had no picture now with the one its page names
        (still without one when none could be found). The order is kept."""
        missing = [index for index, card in enumerate(cards) if card.image_url is None]
        found = await asyncio.gather(*(self._find(cards[index]) for index in missing))
        filled = list(cards)
        for index, image_url in zip(missing, found, strict=True):
            if image_url is not None:
                filled[index] = replace(cards[index], image_url=image_url)
        return filled

    async def close(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

    async def _find(self, card: Card) -> str | None:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                page = await self._read_page(card.url)
        except Exception as error:  # a lookup that fails only leaves the card without a picture
            logger.info("cards: no picture found (%s)", type(error).__name__)
            return None
        if page is None:
            logger.info("cards: no picture found (page not readable)")
            return None
        html, page_url = page
        return find_page_image(html, page_url)

    async def _read_page(self, url: str) -> tuple[str, str] | None:
        """Return the start of the page as text with the address it was read from, following
        a few redirects, or None when it cannot be read."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            target = await self._pinned_target(current)
            if target is None:
                return None
            pinned_url, host = target
            host_header = f"[{host}]" if ":" in host else host
            async with self._http.stream(
                "GET",
                pinned_url,
                headers={
                    "Host": host_header,
                    "User-Agent": USER_AGENT,
                    "Accept-Encoding": "identity",
                },
                extensions={"sni_hostname": host},
            ) as response:
                if response.has_redirect_location:
                    current = urljoin(current, response.headers["location"])
                    continue
                if response.status_code != HTTP_OK or not _is_html(response):
                    return None
                return await self._read_start(response), current
        return None

    async def _pinned_target(self, url: str) -> tuple[str, str] | None:
        """Return the address to connect to (the checked IP in place of the name) and the host
        name to present, or None unless `url` is an `https` address on the default port whose
        name resolves only to public addresses."""
        checked = usable_https_url(url)
        if checked is None:
            return None
        parts = urlsplit(checked)
        host = parts.hostname
        if host is None or parts.port not in (None, HTTPS_PORT) or parts.username is not None:
            return None
        addresses = await self._resolve(host)
        if not addresses or not all(is_public_address(address) for address in addresses):
            return None
        netloc = f"[{addresses[0]}]" if ":" in addresses[0] else addresses[0]
        pinned = urlunsplit(("https", netloc, parts.path or "/", parts.query, ""))
        return pinned, host

    async def _read_start(self, response: httpx.Response) -> str:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size >= self._max_page_bytes:
                break
        return b"".join(chunks)[: self._max_page_bytes].decode("utf-8", errors="replace")


def _is_html(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type")
    return content_type is None or HTML_MARKER in content_type.lower()


async def _resolve_with_system(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, HTTPS_PORT, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))
