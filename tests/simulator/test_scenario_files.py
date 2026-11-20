import json
from pathlib import Path

import pytest

from line_group_agent.simulator.scenario_files import load_scenarios
from line_group_agent.simulator.scenario_parser import ScenarioError

SCENARIO = {
    "name": "Trip",
    "group": {"id": "C1", "name": "G", "members": [{"user_id": "Ua", "name": "Aki"}]},
    "steps": [{"from": "Ua", "text": "hi"}],
}


def write(folder: Path, name: str, content: object = SCENARIO) -> Path:
    path = folder / name
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_a_file_is_one_scenario_named_by_its_file(tmp_path: Path) -> None:
    [scenario] = load_scenarios(write(tmp_path, "01 trip plan.json"))
    assert scenario.slug == "01-trip-plan" and scenario.name == "Trip"


def test_a_folder_gives_its_json_files_in_name_order(tmp_path: Path) -> None:
    write(tmp_path, "b.json")
    write(tmp_path, "a.json")
    (tmp_path / "notes.md").write_text("not a scenario")
    write(tmp_path, ".hidden.json")
    assert [scenario.slug for scenario in load_scenarios(tmp_path)] == ["a", "b"]


def test_an_image_is_found_beside_the_scenario_file(tmp_path: Path) -> None:
    (tmp_path / "menu.png").write_bytes(b"x")
    content = {**SCENARIO, "steps": [{"from": "Ua", "image": "menu.png"}]}
    [scenario] = load_scenarios(write(tmp_path, "a.json", content))
    assert scenario.steps[0].image_file == (tmp_path / "menu.png").resolve()  # type: ignore[union-attr]


def test_the_error_names_the_file(tmp_path: Path) -> None:
    bad = write(tmp_path, "bad.json", {**SCENARIO, "steps": []})
    with pytest.raises(ScenarioError, match="bad.json: steps"):
        load_scenarios(bad)


@pytest.mark.parametrize("text", ["{not json", ""])
def test_a_file_that_is_not_json_is_refused(tmp_path: Path, text: str) -> None:
    path = tmp_path / "a.json"
    path.write_text(text)
    with pytest.raises(ScenarioError, match="cannot read the scenario file"):
        load_scenarios(path)


def test_a_missing_path_or_an_empty_folder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="cannot find"):
        load_scenarios(tmp_path / "nothing.json")
    with pytest.raises(ScenarioError, match="no scenario files"):
        load_scenarios(tmp_path)


def test_two_files_cannot_make_the_same_folder_name(tmp_path: Path) -> None:
    write(tmp_path, "a b.json")
    write(tmp_path, "a-b.json")
    with pytest.raises(ScenarioError, match="same folder name"):
        load_scenarios(tmp_path)
