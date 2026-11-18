import random

import pytest

from line_group_agent.bills.settlement import EXACT_LIMIT, settle


def apply(balances: dict[str, int], transfers: list) -> dict[str, int]:
    after = dict(balances)
    for transfer in transfers:
        after[transfer.payer_name] += transfer.amount
        after[transfer.receiver_name] -= transfer.amount
    return after


def fewest(values: list[int]) -> int:
    """The least number of transfers by trying every way to settle the first balance."""
    values = [v for v in values if v]
    if not values:
        return 0
    first, rest = values[0], values[1:]
    best = len(values)
    for index, other in enumerate(rest):
        if first * other < 0:
            merged = [*rest[:index], other + first, *rest[index + 1 :]]
            best = min(best, 1 + fewest(merged))
    return best


def test_two_people_settle_with_one_transfer() -> None:
    [transfer] = settle({"Aki": 3000, "Sora": -3000})
    assert (transfer.payer_name, transfer.receiver_name, transfer.amount) == ("Sora", "Aki", 3000)


def test_people_with_nothing_to_settle_take_no_part() -> None:
    assert settle({"Aki": 0, "Sora": 0}) == []
    assert [t.payer_name for t in settle({"Aki": 5, "Sora": -5, "Bo": 0})] == ["Sora"]


def test_independent_groups_are_settled_among_themselves() -> None:
    balances = {"a": 4, "b": -4, "c": 3, "d": 2, "e": -5}
    transfers = settle(balances)
    assert len(transfers) == 3
    assert set(apply(balances, transfers).values()) == {0}


def test_a_big_group_still_settles_everyone() -> None:
    names = [f"m{n}" for n in range(EXACT_LIMIT + 4)]
    balances = {name: (n % 5 + 1) * (1 if n % 2 else -1) for n, name in enumerate(names)}
    balances[names[0]] -= sum(balances.values())
    assert set(apply(balances, settle(balances)).values()) == {0}


@pytest.mark.parametrize("seed", range(30))
def test_the_number_of_transfers_is_the_fewest(seed: int) -> None:
    generator = random.Random(seed)
    count = generator.randint(2, 8)
    values = [generator.randint(-9, 9) for _ in range(count - 1)]
    values.append(-sum(values))
    balances = {f"m{n}": value for n, value in enumerate(values)}
    transfers = settle(balances)
    assert set(apply(balances, transfers).values()) == {0}
    assert len(transfers) == fewest(values)
