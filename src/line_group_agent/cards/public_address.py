"""Tell whether an IP address is one a page may be fetched from: a public one.

Pure judgement, no I/O; called by the card image finder before it opens a connection, so
that a card address cannot point the agent at the machine it runs on or at a private network.
"""

from __future__ import annotations

import ipaddress


def is_public_address(text: str) -> bool:
    """Return whether `text` is an IPv4 or IPv6 address on the public internet. Loopback,
    private, link-local, shared (carrier-grade NAT), multicast, reserved and unspecified
    addresses are not, and an IPv6 address that wraps an IPv4 one is judged by the IPv4 one."""
    try:
        address = ipaddress.ip_address(text.split("%", maxsplit=1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not (address.is_multicast or address.is_reserved)
