"""Find the title a web page gives itself: its `og:title`, else its `<title>`.

Pure parsing, no I/O; called by the card image finder with the start of a page, to check that
the page is about the card before the page's picture is used.
"""

from __future__ import annotations

from html.parser import HTMLParser

TITLE_META_KEY = "og:title"


def find_page_title(html: str) -> str | None:
    """Return the page's title (its `og:title` when it has one, else its `<title>`), or None
    when the page gives none."""
    parser = _TitleParser()
    parser.feed(html)
    return parser.meta_title or parser.tag_title.strip() or None


class _TitleParser(HTMLParser):
    """Collects the first `og:title` `content` and the text of the first `<title>`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta_title = ""
        self.tag_title = ""
        self._is_in_title = False
        self._has_title_tag = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title" and not self._has_title_tag:
            self._is_in_title = self._has_title_tag = True
        elif tag == "meta":
            values = {name.lower(): value for name, value in attrs if value is not None}
            key = (values.get("property") or values.get("name") or "").strip().lower()
            if key == TITLE_META_KEY and not self.meta_title:
                self.meta_title = values.get("content", "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._is_in_title = False

    def handle_data(self, data: str) -> None:
        if self._is_in_title:
            self.tag_title += data
