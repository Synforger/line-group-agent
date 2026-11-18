from line_group_agent.liff.request_limiter import RequestLimiter


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
