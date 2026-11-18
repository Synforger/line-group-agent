"""Find the picture a web page names for itself: its `og:image`, else its `twitter:image`.

Pure parsing, no I/O; called by the card image finder with the start of a page. A page that
names several pictures gives the first of each kind; an address that is not a usable `https`
address (see the card input) is passed over for the next kind.
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

from line_group_agent.cards.card_input import usable_https_url

# The kinds of picture a page may name, best first.
IMAGE_META_KEYS = ("og:image", "twitter:image")


def find_page_image(html: str, page_url: str) -> str | None:
    """Return the address of the page's picture, made absolute against `page_url`, or None
    when the page names none that is a usable `https` address."""
    parser = _ImageMetaParser()
    parser.feed(html)
    for key in IMAGE_META_KEYS:
        content = parser.found.get(key)
        if content is None:
            continue
        try:
            address = usable_https_url(urljoin(page_url, content))
        except ValueError:
            continue
        if address is not None:
            return address
    return None


class _ImageMetaParser(HTMLParser):
    """Collects the first `content` of each wanted `<meta>` key, read from `property` or
    `name` (pages use either)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        values = {name.lower(): value for name, value in attrs if value is not None}
        key = (values.get("property") or values.get("name") or "").strip().lower()
        content = values.get("content", "").strip()
        if key in IMAGE_META_KEYS and content and key not in self.found:
            self.found[key] = content
