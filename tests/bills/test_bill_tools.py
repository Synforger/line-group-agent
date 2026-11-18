import json
from typing import Any

import pytest

from line_group_agent.agent.client_tool import ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import TurnOutput
from line_group_agent.bills.bill_tools import MAX_AMOUNT_YEN, bill_tools
from line_group_agent.records.group_log import GroupMessage

TURN = ToolTurn("Cgroup", GroupMessage("t", "1", "U1", "Aki", "@bot split"), TurnOutput())
[TOOL] = bill_tools()


def run(tool_input: object) -> ToolOutcome:
    return TOOL.run(tool_input, TURN)


def entry(payer: str = "Aki", amount: object = 9000, target: object = "all") -> dict[str, Any]:
    return {"payer": payer, "amount": amount, "for": target}


def test_the_result_has_each_balance_the_settlement_and_the_notes() -> None:
    outcome = run({"entries": [entry()], "members": ["Aki", "Sora", "Bo"]})
    assert not outcome.is_error
    result = json.loads(outcome.content)
    assert result["currency"] == "JPY" and result["total_paid"] == 9000
    assert result["members"][0] == {"name": "Aki", "paid": 9000, "share": 3000, "net": 6000}
    assert {(t["from"], t["to"], t["amount"]) for t in result["settlement"]} == {
        ("Sora", "Aki", 3000),
        ("Bo", "Aki", 3000),
    }
    assert result["yen_taken_by_payers"] == 0
    assert any("fraction of a yen" in note for note in result["notes"])


def test_names_are_matched_without_regard_to_case_and_spaces() -> None:
    outcome = run(
        {"entries": [entry(" aki ", 2000, [" SORA", "bo"])], "members": ["Aki", "Sora", "Bo"]}
    )
    result = json.loads(outcome.content)
    assert [m["net"] for m in result["members"]] == [2000, -1000, -1000]
    assert [m["name"] for m in result["members"]] == ["Aki", "Sora", "Bo"]


def test_a_whole_number_written_as_a_float_is_accepted() -> None:
    assert not run({"entries": [entry(amount=3000.0)], "members": ["Aki", "Sora"]}).is_error


@pytest.mark.parametrize(
    "amount", [0, -5, 10.5, "3000", True, None, MAX_AMOUNT_YEN + 1, float("inf")]
)
def test_an_amount_that_is_not_whole_yen_is_refused(amount: object) -> None:
    outcome = run({"entries": [entry(amount=amount)], "members": ["Aki", "Sora"]})
    assert outcome.is_error and "amount" in outcome.content


@pytest.mark.parametrize(
    "entries",
    [
        [entry("Nobody")],
        [entry(target=["Nobody"])],
        [entry(target=[])],
        [entry(target="some")],
        [{"payer": "Aki", "amount": 100}],
        ["not an object"],
        [],
        "nothing",
    ],
)
def test_entries_that_do_not_fit_the_members_are_refused(entries: object) -> None:
    outcome = run({"entries": entries, "members": ["Aki", "Sora"]})
    assert outcome.is_error and "Nothing was calculated" in outcome.content


@pytest.mark.parametrize(
    "members", [["Aki"], ["Aki", "aki"], ["Aki", ""], "Aki Sora", None, ["Aki", 3]]
)
def test_members_must_be_two_or_more_different_names(members: object) -> None:
    assert run({"entries": [entry()], "members": members}).is_error


def test_a_missing_input_is_refused() -> None:
    assert run(None).is_error
