import pytest

from line_group_agent.simulator.scenario_runner import liff_page_path


@pytest.mark.parametrize(
    ("liff_url_path", "expected"),
    [
        ("/1234567890-AbCdEfGh/itinerary", "/liff/itinerary"),
        ("/1234567890-AbCdEfGh/itinerary/", "/liff/itinerary/"),
        ("/1234567890-AbCdEfGh", "/liff/"),
        ("/1234567890-AbCdEfGh/", "/liff/"),
    ],
)
def test_a_liff_address_opens_the_endpoint_with_the_rest_of_its_path_added(
    liff_url_path: str, expected: str
) -> None:
    assert liff_page_path(liff_url_path) == expected
