from line_group_agent.cards.page_image_parser import find_page_image

PAGE = "https://example.com/hotels/gion?x=1"


def head(*metas: str) -> str:
    return f"<html><head><title>t</title>{''.join(metas)}</head><body><p>hi</p></body></html>"


def test_the_og_image_is_taken() -> None:
    html = head('<meta property="og:image" content="https://cdn.example.com/a.jpg">')
    assert find_page_image(html, PAGE) == "https://cdn.example.com/a.jpg"


def test_the_twitter_image_is_taken_when_there_is_no_og_image() -> None:
    html = head('<meta name="twitter:image" content="https://cdn.example.com/t.jpg">')
    assert find_page_image(html, PAGE) == "https://cdn.example.com/t.jpg"


def test_the_og_image_wins_over_the_twitter_image_in_any_order() -> None:
    html = head(
        '<meta name="twitter:image" content="https://cdn.example.com/t.jpg">',
        '<meta property="og:image" content="https://cdn.example.com/o.jpg">',
    )
    assert find_page_image(html, PAGE) == "https://cdn.example.com/o.jpg"


def test_a_page_that_writes_the_key_as_name_or_in_capitals_is_read() -> None:
    html = head('<META NAME="OG:Image" CONTENT=" https://cdn.example.com/a.jpg ">')
    assert find_page_image(html, PAGE) == "https://cdn.example.com/a.jpg"


def test_the_first_og_image_counts() -> None:
    html = head(
        '<meta property="og:image" content="https://cdn.example.com/1.jpg">',
        '<meta property="og:image" content="https://cdn.example.com/2.jpg">',
    )
    assert find_page_image(html, PAGE) == "https://cdn.example.com/1.jpg"


def test_a_relative_address_is_made_absolute_against_the_page() -> None:
    assert find_page_image(head('<meta property="og:image" content="/img/a.jpg">'), PAGE) == (
        "https://example.com/img/a.jpg"
    )
    assert find_page_image(
        head('<meta property="og:image" content="//cdn.example.com/a.jpg">'), PAGE
    ) == ("https://cdn.example.com/a.jpg")


def test_an_address_that_is_not_https_is_passed_over_for_the_next_kind() -> None:
    html = head(
        '<meta property="og:image" content="http://cdn.example.com/a.jpg">',
        '<meta name="twitter:image" content="https://cdn.example.com/t.jpg">',
    )
    assert find_page_image(html, PAGE) == "https://cdn.example.com/t.jpg"
    only_http = head('<meta property="og:image" content="http://cdn.example.com/a.jpg">')
    assert find_page_image(only_http, PAGE) is None


def test_a_page_without_a_picture_or_with_an_empty_one_gives_none() -> None:
    assert find_page_image(head(), PAGE) is None
    assert find_page_image(head('<meta property="og:image" content="">'), PAGE) is None
    assert find_page_image(head('<meta property="og:image">'), PAGE) is None
    assert find_page_image(head('<meta property="og:title" content="x">'), PAGE) is None
    assert find_page_image("", PAGE) is None


def test_a_page_cut_in_the_middle_is_still_read_as_far_as_it_goes() -> None:
    html = '<html><head><meta property="og:image" content="https://cdn.example.com/a.jpg"><meta pro'
    assert find_page_image(html, PAGE) == "https://cdn.example.com/a.jpg"


def test_an_address_with_a_broken_host_is_passed_over() -> None:
    assert (
        find_page_image(head('<meta property="og:image" content="https://[bad/a.jpg">'), PAGE)
        is None
    )
