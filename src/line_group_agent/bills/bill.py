"""The values of a bill split: what was paid, what each person ends up owing, and who pays
whom.

Plain values; made by the bill tool, read by `split_bill` and the settlement.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BillEntry:
    """One payment: `payer` paid `amount` yen for `beneficiaries` (None means everyone)."""

    payer: str
    amount: int
    beneficiaries: tuple[str, ...] | None


@dataclass(frozen=True)
class PersonBalance:
    """What one person paid, what their share is, and the difference: a positive `net` is
    money they should get back, a negative one is money they owe."""

    name: str
    paid: int
    burden: int
    net: int


@dataclass(frozen=True)
class Transfer:
    """`payer_name` pays `receiver_name` `amount` yen to settle up."""

    payer_name: str
    receiver_name: str
    amount: int


@dataclass(frozen=True)
class BillSplit:
    """The result: every person's balance, the fewest transfers that settle everything, the
    total paid, and the yen that did not divide evenly (taken by the payers)."""

    people: tuple[PersonBalance, ...]
    transfers: tuple[Transfer, ...]
    total: int
    absorbed_remainder: int
