"""The tools the model uses to keep the group's trip itinerary: read it, add, change and remove
one item at a time by its id, set the trip's name and first day, and put back an earlier state.

Members see the itinerary as a card (the next three items and a button to the LIFF page) when
the model reads it with `show_card`, or as images of the plan with `show_image` (drawing
waits, so `get_itinerary` is async; the card replaces the images when they cannot be drawn).
A mention with only the itinerary keyword still gets the text back without the model (the
event dispatcher does that). Called by the service builder, which adds the tools to the client
tools.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.itinerary.item_input import (
    NOTE_MAX_CHARS,
    PLACE_MAX_CHARS,
    TITLE_MAX_CHARS,
    TRIP_TITLE_MAX_CHARS,
    ItemInputError,
    day_of,
    start_date_of,
    text_of,
    time_of,
    url_of,
)
from line_group_agent.itinerary.itinerary import MAX_DAY, Itinerary, ItineraryItem, minutes_of
from line_group_agent.itinerary.itinerary_book import MAX_ITEM_COUNT, ItineraryBook
from line_group_agent.itinerary.itinerary_image_message import (
    build_itinerary_image_message,
    itinerary_image_record_line,
)
from line_group_agent.itinerary.itinerary_images import ItineraryImages
from line_group_agent.itinerary.itinerary_message import (
    build_itinerary_message,
    itinerary_record_line,
)
from line_group_agent.line_api.outgoing_extra import OutgoingExtra

GET_ITINERARY_TOOL_NAME = "get_itinerary"
ADD_ITEM_TOOL_NAME = "add_itinerary_item"
CHANGE_ITEM_TOOL_NAME = "change_itinerary_item"
REMOVE_ITEM_TOOL_NAME = "remove_itinerary_item"
SET_TRIP_TOOL_NAME = "set_itinerary_trip"
RESTORE_TOOL_NAME = "restore_itinerary"
NO_ITINERARY_RESULT = "No itinerary is saved for this group yet."
NO_ITEM_RESULT = "No item has that id. Call get_itinerary to see the ids."
TOO_MANY_RESULT = f"The itinerary already holds {MAX_ITEM_COUNT} items, the most it keeps."
NO_TRIP_FIELD_RESULT = "Give a title, a start_date or both; nothing was changed."
NO_VERSION_RESULT = "There is no such earlier version. get_itinerary lists them."
END_AFTER_START_RESULT = (
    "end must be later than start on the same day. An item that runs past midnight ends at "
    "23:59; put the rest on the next day."
)
NO_ROOM_NOTE = "No card was sent: this reply already holds as many extra messages as LINE allows."
NO_PAGE_NOTE = "No card was sent: no itinerary page is set up here, so give the plan in your reply."
EMPTY_CARD_NOTE = "No card was sent: there is nothing on the itinerary yet."
NO_IMAGE_SETUP_NOTE = "No image was sent: images are not set up here."
NO_IMAGE_ROOM_NOTE = (
    "No image was sent: this reply already holds as many extra messages as LINE allows."
)
EMPTY_IMAGE_NOTE = "No image was sent: there is nothing on the itinerary yet."
IMAGE_FAILED_NOTE = "No image was sent: it could not be drawn, so the card is sent instead."
LEGACY_NOTE = (
    "Earlier memo (written before items existed; when asked, turn it into items with "
    "add_itinerary_item and leave it as it is):"
)
FIELD_CLEANERS: dict[str, Callable[[object], object]] = {
    "day": day_of,
    "title": lambda raw: text_of(raw, "title", TITLE_MAX_CHARS, is_required=True),
    "start": lambda raw: time_of(raw, "start"),
    "end": lambda raw: time_of(raw, "end"),
    "place": lambda raw: text_of(raw, "place", PLACE_MAX_CHARS),
    "note": lambda raw: text_of(raw, "note", NOTE_MAX_CHARS),
    "url": url_of,
}


def itinerary_tools(
    book: ItineraryBook,
    *,
    liff_id: str | None,
    clock: Callable[[], datetime],
    images: ItineraryImages | None = None,
) -> list[ClientTool]:
    """Return the itinerary tools, working on `book`. With `liff_id` the model may send the
    itinerary as a card that opens the page of that LIFF app; with `images` it may send it as
    images of the plan."""

    async def get(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        itinerary = book.get(turn.group_id)
        if itinerary is None:
            return ToolOutcome(NO_ITINERARY_RESULT)
        fields = tool_input if isinstance(tool_input, dict) else {}
        text = _model_text_of(itinerary, book.versions(turn.group_id))
        wants_card = fields.get("show_card") is True
        if fields.get("show_image") is True:
            note, is_sent = await _send_images(images, turn, itinerary)
            text += "\n" + note
            wants_card = wants_card or not is_sent
        if wants_card:
            text += "\n" + _send_card(book, turn, itinerary, liff_id, clock())
        return ToolOutcome(text)

    def add(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        current = book.get(turn.group_id)
        if current is not None and len(current.items) >= MAX_ITEM_COUNT:
            return ToolOutcome(TOO_MANY_RESULT, is_error=True)
        try:
            cleaned = {name: FIELD_CLEANERS[name](fields.get(name)) for name in FIELD_CLEANERS}
            _check_times(cleaned["start"], cleaned["end"])
        except ItemInputError as error:
            return ToolOutcome(f"{error} Nothing was added.", is_error=True)
        item = book.add_item(turn.group_id, **cleaned)  # type: ignore[arg-type]
        return ToolOutcome(f"Added day {item.day}: {item.line(with_id=True)}")

    def change(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        found = _item_of(book.get(turn.group_id), fields.get("id"))
        if found is None:
            return ToolOutcome(NO_ITEM_RESULT, is_error=True)
        try:
            changes = {
                name: FIELD_CLEANERS[name](fields[name])
                for name in FIELD_CLEANERS
                if name in fields
            }
            start = changes["start"] if "start" in changes else found.start
            end = changes["end"] if "end" in changes else found.end
            if start is None:
                end = changes["end"] = None
            _check_times(start, end)
        except ItemInputError as error:
            return ToolOutcome(f"{error} Nothing was changed.", is_error=True)
        changed = book.change_item(turn.group_id, found.id, changes)
        if changed == found:
            return ToolOutcome("That is already how the item is; nothing changed.")
        return ToolOutcome(f"Changed day {changed.day}: {changed.line(with_id=True)}")  # type: ignore[union-attr]

    def remove(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        found = _item_of(book.get(turn.group_id), fields.get("id"))
        if found is None or book.remove_item(turn.group_id, found.id) is None:
            return ToolOutcome(NO_ITEM_RESULT, is_error=True)
        return ToolOutcome(f"Removed: {found.line(with_id=True)}. The earlier version is kept.")

    def set_trip(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        try:
            changes: dict[str, str | None] = {}
            if "title" in fields:
                changes["title"] = text_of(fields["title"], "title", TRIP_TITLE_MAX_CHARS)
            if "start_date" in fields:
                changes["start_date"] = start_date_of(fields["start_date"])
        except ItemInputError as error:
            return ToolOutcome(f"{error} Nothing was changed.", is_error=True)
        if not changes:
            return ToolOutcome(NO_TRIP_FIELD_RESULT, is_error=True)
        if not book.change_trip(turn.group_id, changes):
            return ToolOutcome("That is already how the trip is set; nothing changed.")
        return ToolOutcome("The trip is set. The earlier version is kept.")

    def restore(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        raw = tool_input.get("version", 1) if isinstance(tool_input, dict) else 1
        version = raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
        restored = book.restore(turn.group_id, version)
        if restored is None:
            return ToolOutcome(NO_VERSION_RESULT, is_error=True)
        return ToolOutcome(
            f"Version {version} is back as the itinerary ({len(restored.items)} items). "
            "The state it replaced is kept as version 1."
        )

    return [
        ClientTool(GET_ITINERARY_TOOL_NAME, _get_definition(), get),
        ClientTool(ADD_ITEM_TOOL_NAME, _add_definition(), add),
        ClientTool(CHANGE_ITEM_TOOL_NAME, _change_definition(), change),
        ClientTool(REMOVE_ITEM_TOOL_NAME, _remove_definition(), remove),
        ClientTool(SET_TRIP_TOOL_NAME, _set_trip_definition(), set_trip),
        ClientTool(RESTORE_TOOL_NAME, _restore_definition(), restore),
    ]


def _check_times(start: object, end: object) -> None:
    if end is not None and start is None:
        raise ItemInputError("end needs a start.")
    if isinstance(start, str) and isinstance(end, str) and minutes_of(end) <= minutes_of(start):
        raise ItemInputError(END_AFTER_START_RESULT)


def _item_of(itinerary: Itinerary | None, item_id: object) -> ItineraryItem | None:
    if itinerary is None or not isinstance(item_id, str):
        return None
    return next((item for item in itinerary.items if item.id == item_id.strip()), None)


def _model_text_of(itinerary: Itinerary, versions: list[Itinerary]) -> str:
    """Return the itinerary as the model reads it: the trip, each day's items with their ids,
    the earlier memo when there is one, and the earlier versions."""
    start = itinerary.start_date or "not set"
    lines = [
        f"Trip: {itinerary.title or '(no name)'}; day 1 is {start}; "
        f"saved {itinerary.saved_at}; {len(itinerary.items)} items."
    ]
    current_day = 0
    for item in itinerary.sorted_items():
        if item.day != current_day:
            current_day = item.day
            lines.append(itinerary.day_heading(current_day))
        lines.append("  " + item.line(with_id=True))
    if itinerary.legacy_text:
        lines.extend([LEGACY_NOTE, itinerary.legacy_text])
    for number, version in enumerate(versions, start=1):
        lines.append(
            f"Earlier version {number}: saved {version.saved_at}, {len(version.items)} items"
        )
    return "\n".join(lines)


def _send_card(
    book: ItineraryBook, turn: ToolTurn, itinerary: Itinerary, liff_id: str | None, now: datetime
) -> str:
    """Add the itinerary's card to the reply and say so, or say why it was not added."""
    if liff_id is None:
        return NO_PAGE_NOTE
    if not itinerary.items:
        return EMPTY_CARD_NOTE
    if not turn.output.has_room():
        return NO_ROOM_NOTE
    link_id = book.link_id(turn.group_id)
    shown = replace(itinerary, link_id=link_id or "")
    turn.output.add(
        OutgoingExtra(build_itinerary_message(shown, liff_id, now), itinerary_record_line(shown))
    )
    return "The itinerary card is sent after your reply; members open the whole plan from it."


async def _send_images(
    images: ItineraryImages | None, turn: ToolTurn, itinerary: Itinerary
) -> tuple[str, bool]:
    """Add the images of the itinerary to the reply; return what to tell the model and
    whether any image was added."""
    if images is None:
        return NO_IMAGE_SETUP_NOTE, False
    if not itinerary.items:
        return EMPTY_IMAGE_NOTE, False
    if not turn.output.has_room():
        return NO_IMAGE_ROOM_NOTE, False
    made = await images.create(turn.group_id, itinerary)
    if made is None:
        return IMAGE_FAILED_NOTE, False
    sent = 0
    for url in made.urls:
        if not turn.output.has_room():
            break
        turn.output.add(
            OutgoingExtra(
                build_itinerary_image_message(url), itinerary_image_record_line(itinerary)
            )
        )
        sent += 1
    note = f"{sent} image(s) of the plan are sent after your reply."
    if sent < len(made.urls) or made.omitted_day_count:
        note += " Not every day fits: the card or the page shows the rest."
    return note, True


def _get_definition() -> dict[str, Any]:
    return {
        "name": GET_ITINERARY_TOOL_NAME,
        "description": (
            "Read the group's trip itinerary: the trip's name and first day, every item with "
            "its id grouped by day, and the earlier versions. Call it before you change the "
            "itinerary, and when a member asks what the plan is. With show_card true the "
            "itinerary is also sent as a card after your reply (the next three items and a "
            "button that opens the whole plan as a calendar page): use it when a member wants "
            "to see the plan, not when you only read it to change it. With show_image true the "
            "plan is also sent as up to three images drawn like the calendar page, all days "
            "one under the other: use it when a member asks for the plan as an image and when "
            "you have just finished building it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "show_card": {
                    "type": "boolean",
                    "description": "True to send the itinerary card as well.",
                },
                "show_image": {
                    "type": "boolean",
                    "description": "True to send the itinerary as images as well.",
                },
            },
        },
    }


def _item_properties() -> dict[str, Any]:
    return {
        "day": {
            "type": "integer",
            "description": f"Which day of the trip: 1 is the first day, up to {MAX_DAY}.",
        },
        "title": {
            "type": "string",
            "description": f"What happens, up to {TITLE_MAX_CHARS} characters.",
        },
        "start": {
            "type": "string",
            "description": "Start time, 24-hour HH:MM. Leave it out when the time is not fixed.",
        },
        "end": {
            "type": "string",
            "description": "End time, HH:MM, later than start. Leave it out when unknown.",
        },
        "place": {
            "type": "string",
            "description": f"The place's name or address, up to {PLACE_MAX_CHARS} characters. "
            "The page links it to a map search.",
        },
        "note": {"type": "string", "description": f"Up to {NOTE_MAX_CHARS} characters."},
        "url": {"type": "string", "description": "A page about it, starting with https://."},
    }


def _add_definition() -> dict[str, Any]:
    return {
        "name": ADD_ITEM_TOOL_NAME,
        "description": (
            "Add one item to the group's itinerary and get its id. Use it when members decide "
            "or ask you to write something into the plan: one call per item, never the whole "
            "plan at once. The earlier version is kept."
        ),
        "input_schema": {
            "type": "object",
            "properties": _item_properties(),
            "required": ["day", "title"],
        },
    }


def _change_definition() -> dict[str, Any]:
    properties = {"id": {"type": "string", "description": "The item's id from get_itinerary."}}
    properties.update(_item_properties())
    return {
        "name": CHANGE_ITEM_TOOL_NAME,
        "description": (
            "Change fields of one itinerary item by its id; give only the fields that change. "
            "An empty string clears start, end, place, note or url (clearing start clears end "
            "too). The earlier version is kept. Read the itinerary first for the id."
        ),
        "input_schema": {"type": "object", "properties": properties, "required": ["id"]},
    }


def _remove_definition() -> dict[str, Any]:
    return {
        "name": REMOVE_ITEM_TOOL_NAME,
        "description": (
            "Remove one item from the itinerary by its id. Use it only when a member asks. "
            "The earlier version is kept."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The item's id from get_itinerary."}
            },
            "required": ["id"],
        },
    }


def _set_trip_definition() -> dict[str, Any]:
    return {
        "name": SET_TRIP_TOOL_NAME,
        "description": (
            "Set the trip's name and/or the date of its first day. With the first day set, the "
            "page shows each day's date and weekday. An empty string clears a field. Give only "
            "what changes. The earlier version is kept."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": f"The trip's name, up to {TRIP_TITLE_MAX_CHARS} characters.",
                },
                "start_date": {
                    "type": "string",
                    "description": "The date of day 1, like 2026-11-23.",
                },
            },
        },
    }


def _restore_definition() -> dict[str, Any]:
    return {
        "name": RESTORE_TOOL_NAME,
        "description": (
            "Put back an earlier version of the itinerary as the current one (get_itinerary "
            "lists them, 1 is the newest). Use it when a member asks to undo a change. The state "
            "it replaces is kept as version 1."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "version": {
                    "type": "integer",
                    "description": "Which earlier version; 1 if left out.",
                }
            },
        },
    }
