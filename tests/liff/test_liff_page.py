from line_group_agent.liff.liff_page import PAGE_FILE, load_liff_page


def test_the_liff_id_is_written_into_the_script_as_a_string() -> None:
    page = load_liff_page("1234567890-AbCdEfGh")
    assert 'var LIFF_ID = "1234567890-AbCdEfGh";' in page
    assert "__LIFF_ID__" not in page


def test_a_liff_id_cannot_break_out_of_the_script() -> None:
    page = load_liff_page('"</script><script>alert(1)</script>')
    assert "</script><script>alert(1)" not in page
    assert "\\u003c/script>" in page


def test_the_page_is_one_file_that_draws_with_text_only() -> None:
    source = PAGE_FILE.read_text(encoding="utf-8")
    # Names and options are other members' words: they are only ever set as text.
    assert "innerHTML" not in source and "insertAdjacentHTML" not in source
    assert "document.write" not in source and "eval(" not in source
    assert source.count("<script") == 2 and source.count("<style") == 1


def test_the_page_reads_the_poll_by_a_post_with_the_bearer_token_not_by_its_address() -> None:
    source = PAGE_FILE.read_text(encoding="utf-8")
    assert '"/liff/api/poll"' in source and '"/liff/api/vote"' in source
    assert '"Authorization": "Bearer " + token' in source
    assert "setInterval" not in source and "setTimeout" not in source


def test_the_page_keeps_to_the_phone_width_and_the_dark_mode() -> None:
    source = PAGE_FILE.read_text(encoding="utf-8")
    assert 'name="viewport" content="width=device-width' in source
    assert "prefers-color-scheme: dark" in source
