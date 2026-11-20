"""The stand-in's ID tokens: not signed, only a carrier for who the member is.

The stand-in LINE Login reads a token it made and says what LINE would: the member's id
(`sub`) and name. Made by the runner (for the page's SDK stand-in); read by the stand-in
LINE server. A token is never meant to be trusted, so this is only for a stand-in.
"""

from __future__ import annotations

import base64
import json

TOKEN_PREFIX = "simulated."


def make_id_token(user_id: str, name: str) -> str:
    """Return a token that names this member."""
    payload = json.dumps({"sub": user_id, "name": name}, ensure_ascii=False).encode("utf-8")
    return TOKEN_PREFIX + base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def read_id_token(token: str) -> tuple[str, str] | None:
    """Return `(user_id, name)` from a token `make_id_token` made, or None for anything
    else."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    encoded = token[len(TOKEN_PREFIX) :]
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    user_id, name = payload.get("sub"), payload.get("name")
    if not isinstance(user_id, str) or not isinstance(name, str):
        return None
    return user_id, name
