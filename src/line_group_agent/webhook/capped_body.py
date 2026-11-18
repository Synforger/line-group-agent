"""Read a request's body up to a size, so a huge body is refused instead of held in memory.

Called by the webhook endpoint and by the voting page's API.
"""

from __future__ import annotations

from fastapi import Request


async def read_capped_body(request: Request, max_body_bytes: int) -> bytes | None:
    """Return the body, or None when it is larger than `max_body_bytes`."""
    # Refuse early on a declared length, and still count what actually arrives.
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_body_bytes:
        return None
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_body_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)
