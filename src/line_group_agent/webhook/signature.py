"""Check that a webhook request came from LINE (the `X-Line-Signature` header).

Called by the webhook endpoint before it reads the body as JSON.
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def is_valid_signature(body: bytes, signature: str | None, channel_secret: str) -> bool:
    """Return whether `signature` is the base64 HMAC-SHA256 of the raw `body`.

    The comparison takes the same time whatever the header holds.
    """
    if not signature:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest)
    return hmac.compare_digest(expected, signature.encode("utf-8", errors="replace"))
