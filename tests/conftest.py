"""Shared pytest settings: async tests run on asyncio through `anyio`."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
