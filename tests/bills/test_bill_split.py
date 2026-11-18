from line_group_agent.bills.bill import BillEntry
from line_group_agent.bills.bill_split import split_bill

MEMBERS = ["Aki", "Sora", "Bo"]


def nets(entries: list[BillEntry], members: list[str] = MEMBERS) -> dict[str, int]:
    return {p.name: p.net for p in split_bill(entries, members).people}


def test_a_payment_for_everyone_is_shared_equally() -> None:
    split = split_bill([BillEntry("Aki", 9000, None)], MEMBERS)
    assert [(p.name, p.paid, p.burden, p.net) for p in split.people] == [
        ("Aki", 9000, 3000, 6000),
        ("Sora", 0, 3000, -3000),
        ("Bo", 0, 3000, -3000),
    ]
    assert split.total == 9000 and split.absorbed_remainder == 0
    assert {(t.payer_name, t.receiver_name, t.amount) for t in split.transfers} == {
        ("Sora", "Aki", 3000),
        ("Bo", "Aki", 3000),
    }


def test_a_payment_for_some_people_leaves_the_others_out() -> None:
    assert nets([BillEntry("Aki", 3000, ("Aki", "Sora"))]) == {"Aki": 1500, "Sora": -1500, "Bo": 0}


def test_a_payer_who_is_not_in_the_list_it_was_for_gets_it_all_back() -> None:
    assert nets([BillEntry("Aki", 2000, ("Sora", "Bo"))]) == {
        "Aki": 2000,
        "Sora": -1000,
        "Bo": -1000,
    }


def test_the_remaining_yen_are_taken_by_the_payer_and_the_balances_still_sum_to_zero() -> None:
    split = split_bill([BillEntry("Aki", 1000, None)], MEMBERS)
    assert [p.burden for p in split.people] == [334, 333, 333]
    assert split.absorbed_remainder == 1
    assert sum(p.net for p in split.people) == 0


def test_a_payer_outside_the_people_it_was_for_still_takes_the_remainder() -> None:
    split = split_bill([BillEntry("Bo", 1000, ("Aki", "Sora"))], MEMBERS)
    assert [(p.name, p.burden) for p in split.people] == [("Aki", 500), ("Sora", 500), ("Bo", 0)]
    split = split_bill([BillEntry("Bo", 1001, ("Aki", "Sora"))], MEMBERS)
    assert [p.burden for p in split.people] == [500, 500, 1]
    assert split.absorbed_remainder == 1


def test_several_payments_add_up_and_cancel_out() -> None:
    entries = [BillEntry("Aki", 6000, None), BillEntry("Sora", 3000, None)]
    assert nets(entries) == {"Aki": 3000, "Sora": 0, "Bo": -3000}
    split = split_bill(entries, MEMBERS)
    assert [(t.payer_name, t.receiver_name, t.amount) for t in split.transfers] == [
        ("Bo", "Aki", 3000)
    ]


def test_everyone_even_means_nothing_to_settle() -> None:
    entries = [
        BillEntry("Aki", 3000, None),
        BillEntry("Sora", 3000, None),
        BillEntry("Bo", 3000, None),
    ]
    assert split_bill(entries, MEMBERS).transfers == ()
