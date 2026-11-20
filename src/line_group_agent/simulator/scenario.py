"""The shape of one scripted chat: the group, its members and the ordered steps the
members take.

Plain values only; read by the runner and the pages. Built by `scenario_parser`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_BOT_NAME = "Assistant"
DEFAULT_BOT_USER_ID = "Usimulatedbot"


@dataclass(frozen=True)
class Member:
    """A person in the scripted group."""

    user_id: str
    name: str


@dataclass(frozen=True)
class Group:
    """The scripted group: `id` is what the bot sees as the group id."""

    id: str
    name: str
    members: tuple[Member, ...]


@dataclass(frozen=True)
class ActionRef:
    """One button of an earlier bot message: the `reply_index`-th thing the bot sent (counted
    from 0 over every reply and push) and its `action_index`-th action (counted from 0, in
    the order `message_actions.list_actions` gives)."""

    reply_index: int
    action_index: int


@dataclass(frozen=True)
class TextStep:
    """A member writes a message; with `mention` it is addressed to the bot the way LINE's
    @-mention does it."""

    sender: str
    text: str
    mention: bool = False


@dataclass(frozen=True)
class ImageStep:
    """A member sends a photo kept in `image_file`."""

    sender: str
    image_file: Path


@dataclass(frozen=True)
class LocationStep:
    """A member shares a pin."""

    sender: str
    title: str
    address: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class PressStep:
    """A member presses a card button or a quick reply button of an earlier bot message."""

    sender: str
    target: ActionRef


@dataclass(frozen=True)
class OpenLiffStep:
    """A member opens the LIFF page a bot message links to; the page is shown as a screen."""

    sender: str
    target: ActionRef


@dataclass(frozen=True)
class WaitStep:
    """Let `seconds` pass."""

    seconds: float


@dataclass(frozen=True)
class AdvanceStep:
    """Move the bot's clock forward by `minutes` and let it run its timed work once (the
    reminders that come due are sent)."""

    minutes: int


Step = TextStep | ImageStep | LocationStep | PressStep | OpenLiffStep | WaitStep | AdvanceStep


@dataclass(frozen=True)
class Scenario:
    """One scripted chat. `slug` names its folder in the output."""

    slug: str
    name: str
    group: Group
    steps: tuple[Step, ...]
    bot_name: str = DEFAULT_BOT_NAME
    bot_user_id: str = DEFAULT_BOT_USER_ID

    def member_named(self, user_id: str) -> Member:
        """Return the member with this id."""
        for member in self.group.members:
            if member.user_id == user_id:
                return member
        raise KeyError(user_id)
