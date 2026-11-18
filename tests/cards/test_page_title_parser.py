from line_group_agent.cards.page_title_parser import find_page_title


def test_the_og_title_comes_before_the_title_tag() -> None:
    html = '<title>Tab</title><meta property="og:title" content="Shared name">'
    assert find_page_title(html) == "Shared name"


def test_the_title_tag_is_read_when_there_is_no_og_title() -> None:
    assert (
        find_page_title("<head><title>\n  Gion Inn | stay \n</title></head>") == "Gion Inn | stay"
    )


def test_the_og_title_may_be_written_with_name() -> None:
    assert find_page_title('<meta name="og:title" content="Gion Inn">') == "Gion Inn"


def test_the_first_of_each_is_taken() -> None:
    html = "<title>One</title><title>Two</title>"
    assert find_page_title(html) == "One"
    assert (
        find_page_title(
            '<meta property="og:title" content="A"><meta property="og:title" content="B">'
        )
        == "A"
    )


def test_character_references_are_read() -> None:
    assert find_page_title("<title>Tom &amp; Jerry</title>") == "Tom & Jerry"


def test_a_page_without_a_title_gives_none() -> None:
    assert find_page_title("<html><body>x</body></html>") is None
    assert find_page_title("<title>  </title>") is None
    assert find_page_title('<meta property="og:title" content="">') is None
