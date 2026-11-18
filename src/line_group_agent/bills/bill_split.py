"""Work out who owes what for a trip's payments.

Each payment is divided among the people it was for, in whole yen. When it does not divide
evenly, the remaining yen (fewer than one per person) are taken by the person who paid, so
nobody is asked for a fraction of a yen and the balances still sum to zero. The transfers
that settle everything are the fewest possible (see `settlement`).

Pure calculation, no I/O; called by the bill tool.
"""

from __future__ import annotations

from collections.abc import Sequence

from line_group_agent.bills.bill import BillEntry, BillSplit, PersonBalance
from line_group_agent.bills.settlement import settle


def split_bill(entries: Sequence[BillEntry], members: Sequence[str]) -> BillSplit:
    """Return each member's balance and the transfers that settle them.

    Every payer and every person a payment is for must be in `members` (checked by the
    caller), and each payment must be a positive whole number of yen.
    """
    paid = dict.fromkeys(members, 0)
    burden = dict.fromkeys(members, 0)
    absorbed = 0
    for entry in entries:
        people = list(members) if entry.beneficiaries is None else list(entry.beneficiaries)
        share, remainder = divmod(entry.amount, len(people))
        for name in people:
            burden[name] += share
        paid[entry.payer] += entry.amount
        burden[entry.payer] += remainder
        absorbed += remainder
    balances = {
        name: PersonBalance(name, paid[name], burden[name], paid[name] - burden[name])
        for name in members
    }
    transfers = settle({name: balance.net for name, balance in balances.items()})
    return BillSplit(
        people=tuple(balances.values()),
        transfers=tuple(transfers),
        total=sum(paid.values()),
        absorbed_remainder=absorbed,
    )
