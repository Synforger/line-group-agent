"""The bot's time during a simulated scenario: the machine's time plus what the scenario
has moved it forward.

Given to the bot as its clock and moved by the runner at an `advance_minutes` step; the
bot is not told it is simulated.
"""

from __future__ import annotations

from datetime import datetime, timedelta


class ScenarioClock:
    """A clock that reads the machine's time and can be moved forward."""

    def __init__(self) -> None:
        self._offset = timedelta()

    def __call__(self) -> datetime:
        return datetime.now().astimezone() + self._offset

    def advance(self, minutes: int) -> None:
        """Move the clock forward."""
        self._offset += timedelta(minutes=minutes)
