"""Turn the parsed JSON of one scenario file into a `Scenario`, checking every field.

Pure apart from looking at whether an image file exists; called by `scenario_files`.
Every problem is a `ScenarioError` that names the step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from line_group_agent.records.group_log import GROUP_ID_PATTERN
from line_group_agent.simulator.scenario import (
    DEFAULT_BOT_NAME,
    DEFAULT_BOT_USER_ID,
    ActionRef,
    AdvanceStep,
    Group,
    ImageStep,
    LiffClickStep,
    LocationStep,
    Member,
    OpenLiffStep,
    PressStep,
    Scenario,
    Step,
    TextStep,
    WaitStep,
)

MAX_WAIT_SECONDS = 600.0
MAX_ADVANCE_MINUTES = 60 * 24 * 90


class ScenarioError(ValueError):
    """A scenario file is missing a field or holds one of the wrong kind."""


def parse_scenario(raw: Any, base_dir: Path, slug: str) -> Scenario:
    """Build the scenario from its parsed JSON; relative image paths are taken from
    `base_dir` (the scenario file's folder)."""
    document = _object(raw, "the scenario")
    group = _parse_group(_object(document.get("group"), "group"))
    member_ids = [member.user_id for member in group.members]
    bot = _optional_object(document, "bot")
    steps = document.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ScenarioError("steps must be a non-empty list")
    return Scenario(
        slug=slug,
        name=_string(document, "name", "the scenario"),
        group=group,
        steps=tuple(
            _parse_step(step, number, member_ids, base_dir) for number, step in enumerate(steps)
        ),
        bot_name=_optional_string(bot, "name", DEFAULT_BOT_NAME),
        bot_user_id=_optional_string(bot, "user_id", DEFAULT_BOT_USER_ID),
    )


def _parse_group(group: dict[str, Any]) -> Group:
    group_id = _string(group, "id", "group")
    if not GROUP_ID_PATTERN.match(group_id):
        raise ScenarioError("group.id must be letters and digits only (up to 64)")
    raw_members = group.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise ScenarioError("group.members must be a non-empty list")
    members = tuple(
        Member(_string(member, "user_id", "a member"), _string(member, "name", "a member"))
        for member in (_object(item, "a member") for item in raw_members)
    )
    if len({member.user_id for member in members}) != len(members):
        raise ScenarioError("group.members holds the same user_id twice")
    return Group(group_id, _string(group, "name", "group"), members)


def _parse_step(raw: Any, number: int, member_ids: list[str], base_dir: Path) -> Step:
    where = f"step {number}"
    step = _object(raw, where)
    if "wait_seconds" in step:
        seconds = step["wait_seconds"]
        if isinstance(seconds, bool) or not isinstance(seconds, int | float):
            raise ScenarioError(f"{where}: wait_seconds must be a number")
        if not 0 <= seconds <= MAX_WAIT_SECONDS:
            raise ScenarioError(f"{where}: wait_seconds must be between 0 and {MAX_WAIT_SECONDS}")
        return WaitStep(float(seconds))
    if "advance_minutes" in step:
        minutes = step["advance_minutes"]
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise ScenarioError(f"{where}: advance_minutes must be a whole number")
        if not 1 <= minutes <= MAX_ADVANCE_MINUTES:
            raise ScenarioError(
                f"{where}: advance_minutes must be between 1 and {MAX_ADVANCE_MINUTES}"
            )
        return AdvanceStep(minutes)
    is_liff = "open_liff" in step or "liff_click" in step
    sender = step.get("from", member_ids[0] if is_liff else None)
    if sender not in member_ids:
        raise ScenarioError(f"{where}: from must be the user_id of a member of the group")
    if "text" in step:
        return TextStep(sender, _string(step, "text", where), step.get("mention") is True)
    if "image" in step:
        image_file = base_dir / _string(step, "image", where)
        if not image_file.is_file():
            raise ScenarioError(f"{where}: the image file {image_file} does not exist")
        return ImageStep(sender, image_file)
    if "location" in step:
        return _parse_location(sender, _object(step["location"], f"{where}: location"), where)
    if "press" in step:
        return PressStep(sender, _parse_target(step["press"], where))
    if "open_liff" in step:
        return OpenLiffStep(sender, _parse_target(step["open_liff"], where))
    if "liff_click" in step:
        click = _object(step["liff_click"], f"{where}: liff_click")
        return LiffClickStep(sender, _parse_target(click, where), _string(click, "selector", where))
    raise ScenarioError(
        f"{where}: needs one of text, image, location, press, open_liff, liff_click, "
        "wait_seconds or advance_minutes"
    )


def _parse_location(sender: str, raw: dict[str, Any], where: str) -> LocationStep:
    coordinates = []
    for key in ("latitude", "longitude"):
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ScenarioError(f"{where}: location.{key} must be a number")
        coordinates.append(float(value))
    return LocationStep(
        sender,
        _optional_string(raw, "title", ""),
        _optional_string(raw, "address", ""),
        coordinates[0],
        coordinates[1],
    )


def _parse_target(raw: Any, where: str) -> ActionRef:
    target = _object(raw, f"{where}: the target")
    indexes = []
    for key in ("reply_index", "action_index"):
        value = target.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ScenarioError(f"{where}: {key} must be a whole number from 0")
        indexes.append(value)
    return ActionRef(indexes[0], indexes[1])


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioError(f"{where} must be a JSON object")
    return value


def _optional_object(section: dict[str, Any], key: str) -> dict[str, Any]:
    value = section.get(key)
    return {} if value is None else _object(value, key)


def _string(section: dict[str, Any], key: str, where: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ScenarioError(f"{where}: {key} must be a non-empty string")
    return value


def _optional_string(section: dict[str, Any], key: str, default: str) -> str:
    value = section.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ScenarioError(f"{key} must be a string")
    return value.strip()
