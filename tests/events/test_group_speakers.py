from line_group_agent.events.group_speakers import speakers_of
from line_group_agent.records.group_log import GroupMessage


def message(user_id: str | None, name: str | None, *, from_bot: bool = False) -> GroupMessage:
    return GroupMessage("t", "m", user_id, name, "hi", from_bot=from_bot)


def test_each_member_is_known_by_the_name_in_the_record() -> None:
    messages = [message("Ua", "Aki"), message("Ub", "Ben"), message("Ua", "Aki")]
    assert speakers_of(messages) == {"Aki": "Ua", "Ben": "Ub"}


def test_a_member_who_changed_their_name_is_known_by_both() -> None:
    assert speakers_of([message("Ua", "Aki"), message("Ua", "Akiko")]) == {
        "Aki": "Ua",
        "Akiko": "Ua",
    }


def test_a_name_two_members_have_is_left_out() -> None:
    assert speakers_of([message("Ua", "Aki"), message("Ub", "Aki"), message("Uc", "Cleo")]) == {
        "Cleo": "Uc"
    }


def test_the_bot_and_messages_without_an_id_or_a_name_are_skipped() -> None:
    messages = [
        message(None, None, from_bot=True),
        message("Ubot", "Sora", from_bot=True),
        message(None, "Imported"),
        message("Ua", None),
        message("Ub", "  "),
    ]
    assert speakers_of(messages) == {}
