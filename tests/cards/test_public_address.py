import pytest

from line_group_agent.cards.public_address import is_public_address


@pytest.mark.parametrize(
    "address", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"]
)
def test_a_public_address_is_allowed(address: str) -> None:
    assert is_public_address(address)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "240.0.0.1",
        "::1",
        "::",
        "fe80::1",
        "fe80::1%en0",
        "fd00::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.5",
        "localhost",
        "",
        "not an address",
    ],
)
def test_a_local_private_or_unreadable_address_is_refused(address: str) -> None:
    assert not is_public_address(address)
