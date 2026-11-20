import httpx
import pytest
from fastapi import FastAPI

from line_group_agent.simulator.local_server import (
    LocalServer,
    loopback_url,
    reserve_loopback_socket,
)

pytestmark = pytest.mark.anyio


async def test_a_server_answers_at_the_address_known_before_it_was_built() -> None:
    reserved = reserve_loopback_socket()
    known_address = loopback_url(reserved)
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    server = LocalServer(app, reserved=reserved)
    assert server.base_url == known_address
    await server.start()
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"{known_address}/ping")
        assert response.json() == {"ok": "yes"}
    finally:
        await server.stop()
        reserved.close()
