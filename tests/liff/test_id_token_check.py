import pytest

from line_group_agent.liff.id_token_check import LINE_ISSUER, user_id_of_claims

CHANNEL = "1234567890"
NOW = 1_800_000_000.0


def claims(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {"iss": LINE_ISSUER, "sub": "U1", "aud": CHANNEL, "exp": NOW + 60}
    return {**base, **changes}


def test_a_token_of_this_channel_that_has_not_expired_gives_the_member() -> None:
    assert user_id_of_claims(claims(), CHANNEL, NOW) == "U1"


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "9999999999"},
        {"aud": [CHANNEL]},
        {"aud": None},
        {"iss": "https://elsewhere.example"},
        {"exp": NOW},
        {"exp": NOW - 1},
        {"exp": "later"},
        {"exp": True},
        {"exp": None},
        {"sub": ""},
        {"sub": 5},
        {"sub": None},
    ],
)
def test_anything_odd_in_the_claims_gives_nobody(changes: dict[str, object]) -> None:
    assert user_id_of_claims(claims(**changes), CHANNEL, NOW) is None


@pytest.mark.parametrize("missing", ["iss", "sub", "aud", "exp"])
def test_a_missing_claim_gives_nobody(missing: str) -> None:
    given = claims()
    del given[missing]
    assert user_id_of_claims(given, CHANNEL, NOW) is None
