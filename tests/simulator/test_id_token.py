import pytest

from line_group_agent.simulator.id_token import make_id_token, read_id_token


def test_a_token_gives_back_who_it_was_made_for() -> None:
    assert read_id_token(make_id_token("Uaki", "あき")) == ("Uaki", "あき")


@pytest.mark.parametrize("token", ["", "plain", "simulated.", "simulated.!!!", "simulated.e30"])
def test_anything_else_is_not_a_token(token: str) -> None:
    assert read_id_token(token) is None
