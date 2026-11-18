from line_group_agent.media.location_record import location_line, shared_location_line


def test_the_line_has_the_name_the_address_and_the_coordinates() -> None:
    assert location_line("Gion Inn", "Kyoto", 35.0036, 135.7756) == (
        "[位置] Gion Inn Kyoto (35.0036, 135.7756)"
    )


def test_an_empty_name_or_address_is_left_out() -> None:
    assert location_line("", "Kyoto", 35.0, 135.0) == "[位置] Kyoto (35.0, 135.0)"
    assert location_line("", "", 35.0, 135.0) == "[位置] (35.0, 135.0)"


def test_coordinates_are_rounded_to_six_places() -> None:
    assert location_line("a", "b", 35.123456789, -135.1) == "[位置] a b (35.123457, -135.1)"


def test_a_shared_location_is_read_from_the_message() -> None:
    message = {
        "type": "location",
        "title": " Gion Inn ",
        "address": "Kyoto",
        "latitude": 35.0036,
        "longitude": 135.7756,
    }
    assert shared_location_line(message) == "[位置] Gion Inn Kyoto (35.0036, 135.7756)"


def test_a_shared_location_without_a_name_is_still_recorded() -> None:
    message = {"type": "location", "latitude": 35, "longitude": 135}
    assert shared_location_line(message) == "[位置] (35, 135)"


def test_a_shared_location_without_usable_coordinates_gives_none() -> None:
    assert shared_location_line({"latitude": "35", "longitude": 135}) is None
    assert shared_location_line({"latitude": True, "longitude": 135}) is None
    assert shared_location_line({"title": "x"}) is None
