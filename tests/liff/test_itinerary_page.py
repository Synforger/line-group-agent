import re

from line_group_agent.liff.liff_page import ITINERARY_PAGE_FILE, load_itinerary_page


def source() -> str:
    return ITINERARY_PAGE_FILE.read_text(encoding="utf-8")


def test_the_liff_id_is_written_into_the_script_as_a_string() -> None:
    page = load_itinerary_page("1234567890-AbCdEfGh")
    assert 'var LIFF_ID = "1234567890-AbCdEfGh";' in page
    assert "__LIFF_ID__" not in page


def test_a_liff_id_cannot_break_out_of_the_script() -> None:
    page = load_itinerary_page('"</script><script>alert(1)</script>')
    assert "</script><script>alert(1)" not in page
    assert "\\u003c/script>" in page


def test_the_page_is_one_file_that_draws_with_text_only() -> None:
    page = source()
    # Titles, places and notes are members' words: they are only ever set as text.
    assert "innerHTML" not in page and "insertAdjacentHTML" not in page
    assert "document.write" not in page and "eval(" not in page
    assert page.count("<script") == 2 and page.count("<style") == 1
    assert page.count("<script src=") == 1 and "static.line-scdn.net/liff" in page


def test_the_page_loads_nothing_from_outside_but_the_liff_sdk() -> None:
    hosts = set(re.findall(r"https://([a-z.-]+)", source()))
    # liff.line.me is only the address written into the message shared to another chat.
    assert hosts == {"static.line-scdn.net", "liff.line.me"}
    assert source().count('"https://liff.line.me/"') == 1


def test_the_page_reads_the_plan_by_a_post_with_the_bearer_token_not_by_its_address() -> None:
    page = source()
    assert '"/liff/api/itinerary"' in page
    assert '"Authorization": "Bearer " + token' in page
    assert 'method: "POST"' in page


def test_the_page_only_opens_links_of_the_two_kinds_it_expects() -> None:
    page = source()
    assert "MAP_PATTERN" in page and "WEB_PATTERN" in page
    assert 'rel="noopener noreferrer"' in page


def test_the_page_keeps_to_the_phone_width_and_the_dark_mode() -> None:
    page = source()
    assert 'name="viewport" content="width=device-width' in page
    assert "prefers-color-scheme: dark" in page
    assert 'name="referrer" content="no-referrer"' in page
