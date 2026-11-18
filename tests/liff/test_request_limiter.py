from line_group_agent.liff.request_limiter import SWEEP_ABOVE_KEYS, RequestLimiter


def test_a_member_is_let_through_up_to_the_limit_in_a_minute() -> None:
    now = [0.0]
    limiter = RequestLimiter(2, clock=lambda: now[0])
    assert [limiter.allow("U1") for _ in range(3)] == [True, True, False]
    now[0] = 59.9
    assert limiter.allow("U1") is False
    now[0] = 60.0
    assert limiter.allow("U1") is True


def test_each_member_has_their_own_count() -> None:
    limiter = RequestLimiter(1)
    assert limiter.allow("U1") is True
    assert limiter.allow("U2") is True
    assert limiter.allow("U1") is False


def test_a_refused_request_does_not_count_against_the_member() -> None:
    now = [0.0]
    limiter = RequestLimiter(1, clock=lambda: now[0])
    limiter.allow("U1")
    now[0] = 30
    assert limiter.allow("U1") is False
    now[0] = 60
    assert limiter.allow("U1") is True


def test_a_key_can_be_looked_at_without_counting_and_counted_without_asking() -> None:
    now = [0.0]
    limiter = RequestLimiter(2, clock=lambda: now[0])
    assert [limiter.is_full("k") for _ in range(3)] == [False, False, False]
    limiter.record("k")
    limiter.record("k")
    assert limiter.is_full("k") is True
    now[0] = 60.0
    assert limiter.is_full("k") is False


def test_keys_that_went_quiet_are_forgotten_so_made_up_keys_do_not_pile_up() -> None:
    now = [0.0]
    limiter = RequestLimiter(1, clock=lambda: now[0])
    for number in range(SWEEP_ABOVE_KEYS + 1):
        limiter.record(f"made-up-{number}")
    now[0] = 61.0
    limiter.record("fresh")
    assert list(limiter._requests) == ["fresh"]
