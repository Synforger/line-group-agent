from line_group_agent.events.mention_limiter import MentionLimiter, MentionVerdict

ANSWER = MentionVerdict.ANSWER


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_mentions_up_to_the_limit_are_answered() -> None:
    limiter = MentionLimiter(2, clock=Clock())
    assert [limiter.check("U1"), limiter.check("U1")] == [ANSWER, ANSWER]


def test_the_first_mention_over_the_limit_is_refused_and_told_the_rest_only_refused() -> None:
    limiter = MentionLimiter(1, clock=Clock())
    limiter.check("U1")
    assert limiter.check("U1") is MentionVerdict.REFUSE_AND_TELL
    assert limiter.check("U1") is MentionVerdict.REFUSE
    assert limiter.check("U1") is MentionVerdict.REFUSE


def test_each_person_has_their_own_count() -> None:
    limiter = MentionLimiter(1, clock=Clock())
    limiter.check("U1")
    assert limiter.check("U2") is ANSWER


def test_the_hour_slides_and_the_person_is_let_through_again() -> None:
    clock = Clock()
    limiter = MentionLimiter(1, clock=clock)
    limiter.check("U1")
    clock.now = 3599
    assert limiter.check("U1") is MentionVerdict.REFUSE_AND_TELL
    clock.now = 3600
    assert limiter.check("U1") is ANSWER


def test_a_person_is_told_again_in_a_later_hour_of_going_over() -> None:
    clock = Clock()
    limiter = MentionLimiter(1, clock=clock)
    limiter.check("U1")
    assert limiter.check("U1") is MentionVerdict.REFUSE_AND_TELL
    clock.now = 4000
    assert limiter.check("U1") is ANSWER
    assert limiter.check("U1") is MentionVerdict.REFUSE_AND_TELL


def test_refused_mentions_are_not_counted_so_they_do_not_extend_the_block() -> None:
    clock = Clock()
    limiter = MentionLimiter(1, clock=clock)
    limiter.check("U1")
    for second in (100, 200, 300):
        clock.now = second
        limiter.check("U1")
    clock.now = 3600
    assert limiter.check("U1") is ANSWER


def test_a_mention_without_a_known_person_is_always_answered() -> None:
    limiter = MentionLimiter(1, clock=Clock())
    assert [limiter.check(None) for _ in range(3)] == [ANSWER] * 3
