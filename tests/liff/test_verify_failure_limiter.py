from line_group_agent.liff.verify_failure_limiter import VerifyFailureLimiter


def test_nothing_is_blocked_until_failures_reach_the_limit_for_all() -> None:
    limiter = VerifyFailureLimiter(3, 10)
    for _ in range(2):
        limiter.record_failure(None)
    assert limiter.blocked_by(None) is None
    limiter.record_failure(None)
    assert limiter.blocked_by(None) == "all"
    assert limiter.blocked_by("1.2.3.4") == "all"


def test_a_source_is_blocked_by_its_own_failures_while_others_are_not() -> None:
    limiter = VerifyFailureLimiter(30, 2)
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert limiter.blocked_by("1.2.3.4") == "source"
    assert limiter.blocked_by("5.6.7.8") is None
    assert limiter.blocked_by(None) is None


def test_failures_without_a_source_count_only_for_all() -> None:
    limiter = VerifyFailureLimiter(30, 1)
    limiter.record_failure(None)
    limiter.record_failure(None)
    assert limiter.blocked_by("1.2.3.4") is None


def test_the_block_ends_when_the_failures_are_a_minute_old() -> None:
    now = [0.0]
    limiter = VerifyFailureLimiter(1, 1, clock=lambda: now[0])
    limiter.record_failure("1.2.3.4")
    now[0] = 59.9
    assert limiter.blocked_by("1.2.3.4") == "all"
    now[0] = 60.0
    assert limiter.blocked_by("1.2.3.4") is None
