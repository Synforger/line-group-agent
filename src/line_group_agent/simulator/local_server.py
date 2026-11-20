"""Run a web app on a free local port inside the running event loop, and stop it cleanly.

Used for both the stand-in LINE server and the bot, so the two run in one process. Called
by the simulation.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket

import uvicorn
from fastapi import FastAPI

LOOPBACK_HOST = "127.0.0.1"
START_TIMEOUT_SECONDS = 30.0
START_POLL_SECONDS = 0.02
# Longer than the 5 s for which the bot's HTTP client keeps an idle connection: with equal
# times, the client could reuse a connection the server was closing and lose a request.
KEEP_ALIVE_SECONDS = 60


def reserve_loopback_socket() -> socket.socket:
    """Bind a free port on the loopback address and return the socket, so the address a server
    will answer at is known before the server is built. Hand it to `LocalServer`."""
    reserved = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    reserved.bind((LOOPBACK_HOST, 0))
    return reserved


def loopback_url(reserved: socket.socket) -> str:
    """Return the address of a server that will answer on the socket `reserved`."""
    return f"http://{LOOPBACK_HOST}:{reserved.getsockname()[1]}"


class ServerStartError(RuntimeError):
    """A local server did not come up."""


class LocalServer:
    """One web app served on `127.0.0.1` at a port the system picked, or at the port of
    `reserved` (from `reserve_loopback_socket`)."""

    def __init__(self, app: FastAPI, *, reserved: socket.socket | None = None) -> None:
        self._reserved = reserved
        config = uvicorn.Config(
            app,
            host=LOOPBACK_HOST,
            port=0,
            log_config=None,
            timeout_keep_alive=KEEP_ALIVE_SECONDS,
        )
        self._server = uvicorn.Server(config)
        self._task: asyncio.Task[None] | None = None

    @property
    def base_url(self) -> str:
        """The address the app answers at, once started."""
        if self._reserved is not None:
            return loopback_url(self._reserved)
        servers = self._server.servers
        if not servers or not servers[0].sockets:
            raise ServerStartError("the server has not started")
        port = servers[0].sockets[0].getsockname()[1]
        return f"http://{LOOPBACK_HOST}:{port}"

    async def start(self) -> None:
        """Start serving and wait until the app is up (its start-up has run)."""
        sockets = [self._reserved] if self._reserved is not None else None
        self._task = asyncio.create_task(self._server.serve(sockets=sockets))
        waited = 0.0
        while not self._server.started:
            if self._task.done():
                raise ServerStartError(
                    "the server stopped while starting"
                ) from self._task.exception()
            if waited > START_TIMEOUT_SECONDS:
                raise ServerStartError("the server did not start in time")
            await asyncio.sleep(START_POLL_SECONDS)
            waited += START_POLL_SECONDS

    async def stop(self) -> None:
        """Ask the server to finish (the app's shutdown runs) and wait for it."""
        if self._task is None:
            return
        self._server.should_exit = True
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
