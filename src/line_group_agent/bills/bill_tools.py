"""The tool the model uses to split a trip's costs: it passes who paid what for whom, the
agent does the sums in code and gives the balances and the fewest transfers back.

Called by the service builder, which adds the tool to the client tools.
"""

from __future__ import annotations

import json
from typing import Any

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.bills.bill import BillEntry, BillSplit
from line_group_agent.bills.bill_split import split_bill

SPLIT_BILL_TOOL_NAME = "split_bill"
MAX_MEMBER_COUNT = 30
MAX_ENTRY_COUNT = 100
MAX_AMOUNT_YEN = 10**9
ALL_MEMBERS = "all"
CURRENCY = "JPY"
ROUNDING_NOTE = (
    "Amounts are whole yen. A payment that does not divide evenly among the people it was for "
    "leaves fewer than one yen per person; the person who paid takes those remaining yen, so "
    "nobody is asked for a fraction of a yen."
)
BALANCE_NOTE = "net > 0: the member should get that much back; net < 0: the member owes it."


def bill_tools() -> list[ClientTool]:
    """Return the bill tool."""
    return [ClientTool(SPLIT_BILL_TOOL_NAME, _definition(), _run)]


def _run(tool_input: object, _turn: ToolTurn) -> ToolOutcome:
    fields = tool_input if isinstance(tool_input, dict) else {}
    members = _members_of(fields.get("members"))
    if members is None:
        return _refused(f"Give 2 to {MAX_MEMBER_COUNT} different member names in members.")
    entries, problem = _entries_of(fields.get("entries"), members)
    if problem is not None or entries is None:
        return _refused(problem or "Give the payments in entries.")
    return ToolOutcome(json.dumps(_result_of(split_bill(entries, list(members.values())))))


def _members_of(raw: object) -> dict[str, str] | None:
    """Return the members keyed by their name in lower case, or None unless there are 2 to
    30 different non-empty names."""
    if not isinstance(raw, list) or not 2 <= len(raw) <= MAX_MEMBER_COUNT:
        return None
    members: dict[str, str] = {}
    for item in raw:
        name = item.strip() if isinstance(item, str) else ""
        if not name or name.casefold() in members:
            return None
        members[name.casefold()] = name
    return members


def _entries_of(raw: object, members: dict[str, str]) -> tuple[list[BillEntry] | None, str | None]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_ENTRY_COUNT:
        return None, f"Give 1 to {MAX_ENTRY_COUNT} payments in entries."
    entries: list[BillEntry] = []
    for number, item in enumerate(raw, start=1):
        entry, problem = _entry_of(item, members)
        if entry is None:
            return None, f"Payment {number}: {problem}"
        entries.append(entry)
    return entries, None


def _entry_of(item: object, members: dict[str, str]) -> tuple[BillEntry | None, str]:
    if not isinstance(item, dict):
        return None, "each payment is an object with payer, amount and for."
    amount = _yen_of(item.get("amount"))
    if amount is None:
        return None, f"amount must be a whole number of yen from 1 to {MAX_AMOUNT_YEN}."
    payer = _resolve(item.get("payer"), members)
    if payer is None:
        return None, f"payer {item.get('payer')!r} is not in members."
    target = item.get("for")
    if target == ALL_MEMBERS:
        return BillEntry(payer, amount, None), ""
    if not isinstance(target, list) or not target:
        return None, f'for must be "{ALL_MEMBERS}" or a list of member names.'
    names: list[str] = []
    for raw_name in target:
        name = _resolve(raw_name, members)
        if name is None:
            return None, f"{raw_name!r} in for is not in members."
        if name not in names:
            names.append(name)
    return BillEntry(payer, amount, tuple(names)), ""


def _resolve(raw: object, members: dict[str, str]) -> str | None:
    return members.get(raw.strip().casefold()) if isinstance(raw, str) else None


def _yen_of(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    amount = int(value)
    return amount if 1 <= amount <= MAX_AMOUNT_YEN else None


def _result_of(split: BillSplit) -> dict[str, Any]:
    return {
        "currency": CURRENCY,
        "total_paid": split.total,
        "members": [
            {"name": p.name, "paid": p.paid, "share": p.burden, "net": p.net} for p in split.people
        ],
        "settlement": [
            {"from": t.payer_name, "to": t.receiver_name, "amount": t.amount}
            for t in split.transfers
        ],
        "yen_taken_by_payers": split.absorbed_remainder,
        "notes": [BALANCE_NOTE, ROUNDING_NOTE],
    }


def _refused(message: str) -> ToolOutcome:
    return ToolOutcome(f"{message} Nothing was calculated.", is_error=True)


def _definition() -> dict[str, Any]:
    return {
        "name": SPLIT_BILL_TOOL_NAME,
        "description": (
            "Split a trip's costs among the members. Give every payment (who paid, how many "
            "yen, and for whom) and the member names; the sums are done exactly in code. It "
            "returns each member's paid amount, share and net balance, and the fewest "
            "transfers that settle everything. Use it instead of calculating yourself. "
            "Amounts are whole yen. Tell the group the settlement and the rounding note."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entries": {
                    "type": "array",
                    "description": "One item per payment.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "payer": {"type": "string", "description": "A name from members."},
                            "amount": {"type": "integer", "description": "Whole yen paid."},
                            "for": {
                                "description": (
                                    f'"{ALL_MEMBERS}" when it was for every member, or the '
                                    "names it was for."
                                ),
                                "anyOf": [
                                    {"type": "string", "enum": [ALL_MEMBERS]},
                                    {"type": "array", "items": {"type": "string"}},
                                ],
                            },
                        },
                        "required": ["payer", "amount", "for"],
                    },
                },
                "members": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"Everyone who shares the costs, 2 to {MAX_MEMBER_COUNT}.",
                },
            },
            "required": ["entries", "members"],
        },
    }
