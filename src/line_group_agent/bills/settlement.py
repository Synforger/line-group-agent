"""Settle up with the fewest transfers.

Everyone's balance sums to zero. The fewest transfers is the number of people with a
balance, minus the most groups that can be settled among themselves (each group's balances
sum to zero and needs one transfer fewer than it has people). Finding that split is checked
exactly for up to `EXACT_LIMIT` people; a bigger group falls back to matching the largest
debt with the largest credit, which is close and always settles.

Pure calculation; called by `split_bill`.
"""

from __future__ import annotations

from line_group_agent.bills.bill import Transfer

EXACT_LIMIT = 14


def settle(balances: dict[str, int]) -> list[Transfer]:
    """Return the transfers that bring every balance to zero (negative pays, positive gets).

    The balances must sum to zero. Names with a zero balance take no part.
    """
    people = sorted(((name, net) for name, net in balances.items() if net != 0))
    if len(people) <= EXACT_LIMIT:
        groups = _zero_sum_groups(people)
    else:
        groups = [people]
    transfers: list[Transfer] = []
    for group in groups:
        transfers.extend(_match(group))
    return transfers


def _zero_sum_groups(people: list[tuple[str, int]]) -> list[list[tuple[str, int]]]:
    count = len(people)
    if count == 0:
        return []
    full = (1 << count) - 1
    sums = [0] * (full + 1)
    for mask in range(1, full + 1):
        low = mask & -mask
        sums[mask] = sums[mask ^ low] + people[low.bit_length() - 1][1]
    best = [0] * (full + 1)
    last = [0] * (full + 1)
    for mask in range(1, full + 1):
        chosen, chosen_value = 0, -1
        for index in range(count):
            if mask >> index & 1 and best[mask ^ (1 << index)] > chosen_value:
                chosen, chosen_value = index, best[mask ^ (1 << index)]
        best[mask] = chosen_value + (1 if sums[mask] == 0 else 0)
        last[mask] = chosen
    groups: list[list[tuple[str, int]]] = []
    current: list[tuple[str, int]] = []
    mask = full
    while mask:
        current.append(people[last[mask]])
        mask ^= 1 << last[mask]
        if sums[mask] == 0:
            groups.append(current)
            current = []
    return groups


def _match(group: list[tuple[str, int]]) -> list[Transfer]:
    debts = sorted(((-net, name) for name, net in group if net < 0), key=lambda d: (-d[0], d[1]))
    credits = sorted(((net, name) for name, net in group if net > 0), key=lambda c: (-c[0], c[1]))
    transfers: list[Transfer] = []
    while debts and credits:
        debt, payer = debts[0]
        credit, receiver = credits[0]
        amount = min(debt, credit)
        transfers.append(Transfer(payer, receiver, amount))
        debts[0], credits[0] = (debt - amount, payer), (credit - amount, receiver)
        if debts[0][0] == 0:
            debts.pop(0)
        if credits[0][0] == 0:
            credits.pop(0)
        debts.sort(key=lambda d: (-d[0], d[1]))
        credits.sort(key=lambda c: (-c[0], c[1]))
    return transfers
