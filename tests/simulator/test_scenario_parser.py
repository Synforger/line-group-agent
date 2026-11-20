from pathlib import Path
from typing import Any

import pytest

from line_group_agent.simulator.scenario import (
    ActionRef,
    ImageStep,
    LocationStep,
    OpenLiffStep,
    PressStep,
    TextStep,
    WaitStep,
)
from line_group_agent.simulator.scenario_parser import ScenarioError, parse_scenario


def document(*steps: dict[str, Any], **changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "name": "Trip",
        "group": {
            "id": "Cgroup1",
            "name": "Friends",
            "members": [{"user_id": "Ua", "name": "Aki"}, {"user_id": "Ub", "name": "Ben"}],
        },
        "steps": list(steps),
    }
    raw.update(changes)
    return raw


def test_every_kind_of_step_is_read(tmp_path: Path) -> None:
    (tmp_path / "menu.jpg").write_bytes(b"x")
    scenario = parse_scenario(
        document(
            {"from": "Ua", "text": "hi", "mention": True},
            {"from": "Ub", "image": "menu.jpg"},
            {"from": "Ua", "location": {"title": "Cafe", "latitude": 35, "longitude": 135.5}},
            {"from": "Ub", "press": {"reply_index": 0, "action_index": 2}},
            {"open_liff": {"reply_index": 1, "action_index": 0}},
            {"wait_seconds": 2},
        ),
        tmp_path,
        "trip",
    )
    assert scenario.steps == (
        TextStep("Ua", "hi", mention=True),
        ImageStep("Ub", tmp_path / "menu.jpg"),
        LocationStep("Ua", "Cafe", "", 35.0, 135.5),
        PressStep("Ub", ActionRef(0, 2)),
        OpenLiffStep("Ua", ActionRef(1, 0)),
        WaitStep(2.0),
    )
    assert scenario.group.id == "Cgroup1" and scenario.bot_name == "Assistant"
    assert scenario.member_named("Ub").name == "Ben"


def test_the_bot_can_be_given_a_name() -> None:
    raw = document({"from": "Ua", "text": "hi"}, bot={"name": "Sora", "user_id": "Usora"})
    scenario = parse_scenario(raw, Path("."), "trip")
    assert (scenario.bot_name, scenario.bot_user_id) == ("Sora", "Usora")


@pytest.mark.parametrize(
    ("step", "message"),
    [
        ({"from": "Unobody", "text": "hi"}, "step 0: from must be the user_id of a member"),
        ({"text": "hi"}, "step 0: from must be the user_id of a member"),
        ({"from": "Ua"}, "step 0: needs one of text"),
        ({"from": "Ua", "text": "  "}, "step 0: text must be a non-empty string"),
        ({"from": "Ua", "image": "missing.png"}, "does not exist"),
        ({"from": "Ua", "location": {"latitude": "x", "longitude": 1}}, "latitude"),
        ({"from": "Ua", "press": {"reply_index": -1, "action_index": 0}}, "reply_index"),
        ({"from": "Ua", "press": {"reply_index": 0}}, "action_index"),
        ({"wait_seconds": "soon"}, "wait_seconds must be a number"),
        ({"wait_seconds": 100000}, "wait_seconds must be between"),
    ],
)
def test_a_bad_step_names_itself(step: dict[str, Any], message: str, tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match=message):
        parse_scenario(document(step), tmp_path, "trip")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"steps": []}, "steps must be a non-empty list"),
        ({"name": ""}, "name must be a non-empty string"),
        (
            {"group": {"id": "a b", "name": "G", "members": [{"user_id": "U", "name": "N"}]}},
            "group.id",
        ),
        ({"group": {"id": "C1", "name": "G", "members": []}}, "group.members"),
        (
            {"group": {"id": "C1", "name": "G", "members": [{"user_id": "U", "name": "A"}] * 2}},
            "twice",
        ),
    ],
)
def test_a_bad_scenario_is_refused(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ScenarioError, match=message):
        parse_scenario(document({"from": "Ua", "text": "hi"}, **changes), Path("."), "trip")


def test_something_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(ScenarioError, match="must be a JSON object"):
        parse_scenario([1], Path("."), "trip")
