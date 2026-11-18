"""Read the text file LINE makes with "send chat history" into messages.

The file starts with a header (`[LINE] …`, the day it was saved), then for each day a date
line and below it one line per message: the time, a tab, the sender's name, a tab and the
text. A text of several lines is wrapped in double quotes (a quote inside it is written
twice). A line with only a time and a text is a notice (someone joined, a message was taken
back). Only this much is relied on, and a line of any other shape is counted and skipped, so
a file in a form not seen before never stops the import.

Pure functions, no I/O; called by the history importer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

# Year first (2026/11/17(Tue), 2026.11.17, 2026-11-17 Tue) or weekday and month first
# (Tue, 11/17/2026). A date line holds nothing else, and no tab.
DATE_YEAR_FIRST = re.compile(r"^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})(?![\d/.\-]).{0,20}$")
DATE_MONTH_FIRST = re.compile(r"^[A-Za-z]{3,9},?\s+(\d{1,2})/(\d{1,2})/(\d{4})$")
TIME_PREFIX = re.compile(r"^(午前|午後|AM|PM)?\s?(\d{1,2}):(\d{2})\s?(AM|PM)?\t", re.IGNORECASE)
HEADER_LINE = re.compile(r"^(\[LINE\]|保存日時|Saved on)", re.IGNORECASE)
UNSENT_NOTICES = ("メッセージの送信を取り消しました", "unsent a message")
QUOTE = '"'
MAX_DATE_LINE_CHARS = 40
NOON_HOUR = 12


@dataclass(frozen=True)
class HistoryMessage:
    """One message of the history: when it was said (the file's own clock, no zone), who said
    it and what."""

    moment: datetime
    name: str
    text: str


@dataclass(frozen=True)
class ParsedHistory:
    """The messages, how many lines were notices (skipped on purpose) and how many lines
    were not understood (skipped and counted)."""

    messages: list[HistoryMessage]
    notice_count: int
    unrecognized_count: int


def parse_history(text: str) -> ParsedHistory:
    """Read the whole file. A message before any date line, a line of an unknown shape and a
    date that is not a real date are counted as not understood."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    messages: list[HistoryMessage] = []
    notices = unrecognized = 0
    day: date | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or HEADER_LINE.match(line):
            continue
        found_day = _day_of(line)
        if found_day is not None:
            day = found_day
            continue
        clock = _clock_of(line)
        if clock is None or day is None:
            unrecognized += 1
            continue
        hour_minute, rest = clock
        fields = rest.split("\t", 1)
        if len(fields) < 2 or not fields[0].strip() or _is_unsent_notice(fields[1]):
            notices += 1
            continue
        body, index = _body_of(fields[1], lines, index)
        moment = datetime(day.year, day.month, day.day, *hour_minute)
        messages.append(HistoryMessage(moment, fields[0].strip(), body))
    return ParsedHistory(messages, notices, unrecognized)


def _day_of(line: str) -> date | None:
    stripped = line.strip()
    if "\t" in stripped or len(stripped) > MAX_DATE_LINE_CHARS:
        return None
    first = DATE_YEAR_FIRST.match(stripped)
    second = DATE_MONTH_FIRST.match(stripped)
    try:
        if first:
            return date(int(first[1]), int(first[2]), int(first[3]))
        if second:
            return date(int(second[3]), int(second[1]), int(second[2]))
    except ValueError:
        return None
    return None


def _clock_of(line: str) -> tuple[tuple[int, int], str] | None:
    """Return the time at the start of a message line (hour and minute, 24-hour) and what
    follows its tab, or None when the line does not start with a time and a tab."""
    found = TIME_PREFIX.match(line)
    if found is None:
        return None
    hour, minute = int(found[2]), int(found[3])
    marker = (found[1] or found[4] or "").casefold()
    if marker in ("pm", "午後") and hour < NOON_HOUR:
        hour += NOON_HOUR
    elif marker in ("am", "午前") and hour == NOON_HOUR:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return (hour, minute), line[found.end() :]


def _body_of(first: str, lines: list[str], next_index: int) -> tuple[str, int]:
    """Return the text of a message and the index of the line after it. A text that starts
    with a quote runs until a line that ends with a closing quote."""
    if not first.startswith(QUOTE):
        return first, next_index
    parts = [first[1:]]
    while not _is_closed(parts[-1]) and next_index < len(lines):
        parts.append(lines[next_index])
        next_index += 1
    joined = "\n".join(parts)
    if _is_closed(joined):
        joined = joined[:-1]
    return joined.replace(QUOTE + QUOTE, QUOTE), next_index


def _is_closed(text: str) -> bool:
    """Whether the text ends with a closing quote: an odd run of quotes (a pair is one
    quote inside the text)."""
    return (len(text) - len(text.rstrip(QUOTE))) % 2 == 1


def _is_unsent_notice(text: str) -> bool:
    folded = text.strip().casefold()
    return any(notice in folded for notice in UNSENT_NOTICES)
