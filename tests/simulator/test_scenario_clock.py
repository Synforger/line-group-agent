from datetime import timedelta

from line_group_agent.simulator.scenario_clock import ScenarioClock


def test_the_clock_reads_the_machines_time_until_it_is_moved() -> None:
    clock = ScenarioClock()
    first = clock()
    assert first.tzinfo is not None and timedelta(0) <= clock() - first < timedelta(seconds=5)


def test_advancing_moves_the_clock_forward_and_adds_up() -> None:
    clock = ScenarioClock()
    before = clock()
    clock.advance(90)
    clock.advance(30)
    moved = clock() - before
    assert timedelta(minutes=120) <= moved < timedelta(minutes=120, seconds=5)
