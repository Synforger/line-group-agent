from datetime import datetime

from line_group_agent.reminders.reminder import GROUP_TIME_ZONE, Reminder
from line_group_agent.reminders.reminder_text import reminder_text

MOMENT = datetime(2026, 11, 20, 21, 0, tzinfo=GROUP_TIME_ZONE)


def test_the_text_goes_as_it_is_with_no_label() -> None:
    assert reminder_text(Reminder("r1", "Gather at 21:00", MOMENT, (), MOMENT)) == "Gather at 21:00"


def test_the_people_to_call_are_written_as_names_before_the_text() -> None:
    reminder = Reminder("r1", "Gather at 21:00", MOMENT, ("Aki", "Ben"), MOMENT)
    assert reminder_text(reminder) == "@Aki @Ben Gather at 21:00"
