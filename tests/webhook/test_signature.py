import base64
import hashlib
import hmac

from line_group_agent.webhook.signature import is_valid_signature

SECRET = "channel-secret"


def sign(body: bytes, secret: str = SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def test_accepts_the_signature_of_the_raw_body() -> None:
    body = b'{"events":[]}'
    assert is_valid_signature(body, sign(body), SECRET)


def test_refuses_a_signature_made_with_another_secret() -> None:
    body = b'{"events":[]}'
    assert not is_valid_signature(body, sign(body, "other"), SECRET)


def test_refuses_a_changed_body() -> None:
    body = b'{"events":[]}'
    assert not is_valid_signature(b'{"events": []}', sign(body), SECRET)


def test_refuses_a_missing_or_empty_header() -> None:
    assert not is_valid_signature(b"{}", None, SECRET)
    assert not is_valid_signature(b"{}", "", SECRET)


def test_refuses_a_header_that_is_not_ascii() -> None:
    assert not is_valid_signature(b"{}", "署名", SECRET)
