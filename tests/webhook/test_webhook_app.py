import asyncio
import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from line_group_agent.webhook.webhook_app import create_app
from tests.webhook.test_signature import SECRET, sign

LIMIT = 1024


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[Any] = []
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def add_events(self, events: list[Any]) -> None:
        self.events.extend(events)


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()


@pytest.fixture
def client(sink: RecordingSink) -> TestClient:
    with TestClient(create_app(SECRET, LIMIT, sink)) as test_client:
        yield test_client


def post(client: TestClient, body: bytes, signature: str | None) -> Any:
    headers = {"content-type": "application/json"}
    if signature is not None:
        headers["x-line-signature"] = signature
    return client.post("/line/webhook", content=body, headers=headers)


def test_a_signed_request_is_answered_200_and_its_events_are_queued(
    client: TestClient, sink: RecordingSink
) -> None:
    body = json.dumps({"events": [{"type": "message"}]}).encode()
    response = post(client, body, sign(body))
    assert response.status_code == 200
    assert sink.events == [{"type": "message"}]


def test_lifespan_starts_and_stops_the_sink(sink: RecordingSink) -> None:
    with TestClient(create_app(SECRET, LIMIT, sink)):
        assert sink.started
    assert sink.stopped


def test_a_bad_signature_is_401_and_nothing_is_queued(
    client: TestClient, sink: RecordingSink, caplog: pytest.LogCaptureFixture
) -> None:
    body = json.dumps({"events": [{"type": "message", "message": {"text": "secret talk"}}]})
    with caplog.at_level(logging.INFO):
        response = post(client, body.encode(), "bm90LWEtc2lnbmF0dXJl")
    assert response.status_code == 401
    assert sink.events == []
    assert "bm90LWEtc2lnbmF0dXJl" not in caplog.text
    assert "secret talk" not in caplog.text
    assert SECRET not in caplog.text


def test_a_missing_signature_is_401(client: TestClient, sink: RecordingSink) -> None:
    assert post(client, b'{"events":[]}', None).status_code == 401
    assert sink.events == []


def test_a_body_over_the_limit_is_413_before_the_signature(
    client: TestClient, sink: RecordingSink
) -> None:
    body = b'{"events":[],"pad":"' + b"x" * LIMIT + b'"}'
    response = post(client, body, sign(body))
    assert response.status_code == 413
    assert sink.events == []


def test_a_streamed_body_over_the_limit_is_413(client: TestClient) -> None:
    def chunks() -> Any:
        for _ in range(4):
            yield b"x" * (LIMIT // 2)

    response = client.post("/line/webhook", content=chunks(), headers={"x-line-signature": "x"})
    assert response.status_code == 413


def test_a_body_at_the_limit_is_read(client: TestClient, sink: RecordingSink) -> None:
    prefix = b'{"events":[],"pad":"'
    body = prefix + b"x" * (LIMIT - len(prefix) - 2) + b'"}'
    assert len(body) == LIMIT
    assert post(client, body, sign(body)).status_code == 200


def test_other_paths_are_404(client: TestClient) -> None:
    for path in ("/", "/docs", "/openapi.json", "/line", "/line/webhook/extra"):
        assert client.post(path).status_code == 404
        assert client.get(path).status_code == 404


def test_other_methods_on_the_webhook_are_405(client: TestClient) -> None:
    assert client.get("/line/webhook").status_code == 405
    assert client.put("/line/webhook").status_code == 405
    assert client.delete("/line/webhook").status_code == 405


def test_the_answer_does_not_wait_for_the_events_to_be_handled() -> None:
    class SlowSink(RecordingSink):
        def __init__(self) -> None:
            super().__init__()
            self.release = asyncio.Event()
            self.finished = False

        def add_events(self, events: list[Any]) -> None:
            super().add_events(events)
            asyncio.get_running_loop().create_task(self._handle())

        async def _handle(self) -> None:
            await self.release.wait()
            self.finished = True

    sink = SlowSink()
    with TestClient(create_app(SECRET, LIMIT, sink)) as test_client:
        body = b'{"events":[{"type":"message"}]}'
        response = post(test_client, body, sign(body))
        assert response.status_code == 200
        assert not sink.finished


def test_a_signed_body_that_is_not_json_is_400(client: TestClient, sink: RecordingSink) -> None:
    body = b"not json"
    assert post(client, body, sign(body)).status_code == 400
    assert sink.events == []
