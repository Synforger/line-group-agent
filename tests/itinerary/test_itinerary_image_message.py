from line_group_agent.itinerary.itinerary import Itinerary
from line_group_agent.itinerary.itinerary_image_message import (
    build_itinerary_image_message,
    itinerary_image_record_line,
)


def test_the_message_names_the_image_as_both_the_picture_and_its_preview() -> None:
    url = "https://bot.example/liff/media/abc.png"
    assert build_itinerary_image_message(url) == {
        "type": "image",
        "originalContentUrl": url,
        "previewImageUrl": url,
    }


def test_the_record_line_carries_the_trips_name_or_a_default() -> None:
    named = Itinerary("Kyoto trip", None, (), "now")
    assert itinerary_image_record_line(named) == "[予定表の画像] Kyoto trip"
    assert (
        itinerary_image_record_line(Itinerary("", None, (), "now")) == "[予定表の画像] 旅の予定表"
    )
