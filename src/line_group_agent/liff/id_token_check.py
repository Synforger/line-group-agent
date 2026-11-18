"""Decide whether the claims LINE read from an ID token are good for this app.

Pure judgement, no I/O; called by the LIFF poll service after LINE's verify call answered.
LINE checks the signature; the audience (our Login channel), the issuer and the expiry are
checked again here so a token made for another channel can never pass.
"""

from __future__ import annotations

from typing import Any

LINE_ISSUER = "https://access.line.me"


def user_id_of_claims(
    claims: dict[str, Any], login_channel_id: str, now_epoch_seconds: float
) -> str | None:
    """Return the member's id (`sub`) when the token was made for this Login channel by LINE
    and has not expired, else None."""
    if claims.get("aud") != login_channel_id or claims.get("iss") != LINE_ISSUER:
        return None
    expires_at = claims.get("exp")
    if isinstance(expires_at, bool) or not isinstance(expires_at, int | float):
        return None
    if expires_at <= now_epoch_seconds:
        return None
    user_id = claims.get("sub")
    return user_id if isinstance(user_id, str) and user_id else None
