from line_group_agent.liff.expiring_memory import ExpiringMemory


def test_a_value_is_remembered_until_its_time_is_up() -> None:
    now = [0.0]
    memory: ExpiringMemory[str, bool] = ExpiringMemory(10, clock=lambda: now[0])
    memory.remember("a", False)
    now[0] = 9.9
    assert memory.get("a") is False
    now[0] = 10.0
    assert memory.get("a") is None


def test_an_unknown_key_gives_none() -> None:
    assert ExpiringMemory[str, str](10).get("a") is None


def test_remembering_again_starts_the_time_over() -> None:
    now = [0.0]
    memory: ExpiringMemory[str, str] = ExpiringMemory(10, clock=lambda: now[0])
    memory.remember("a", "old")
    now[0] = 8
    memory.remember("a", "new")
    now[0] = 15
    assert memory.get("a") == "new"


def test_the_oldest_go_first_when_there_are_too_many() -> None:
    memory: ExpiringMemory[int, int] = ExpiringMemory(100, max_entries=2)
    for key in (1, 2, 3):
        memory.remember(key, key)
    assert [memory.get(key) for key in (1, 2, 3)] == [None, 2, 3]
