"""Draw a scripted chat as one HTML file at a phone's width: each member's bubbles with their
names, the bot's text, Flex cards and carousels, quick reply buttons, photos, pins and the
LIFF pages that were opened, with the seconds and the spend of each step under the answer.

Pure: the photos arrive as ready `data:` addresses so the file stands alone and loads no
CDN. Called by the report writer.
"""

from __future__ import annotations

import zlib
from collections.abc import Mapping
from html import escape
from typing import Any

from line_group_agent.simulator.chat_style import CHAT_CSS
from line_group_agent.simulator.flex_html import FlexHtml
from line_group_agent.simulator.message_actions import action_numbers
from line_group_agent.simulator.transcript import OutputRecord, ScenarioTranscript, StepRecord

AVATAR_COLORS = ("#e57373", "#64b5f6", "#ffb74d", "#81c784", "#ba68c8", "#4db6ac", "#f06292")
QUOTE_MAX_CHARS = 40


def render_chat_page(transcript: ScenarioTranscript, image_uris: Mapping[str, str]) -> str:
    """Return the chat page. `image_uris` maps the file path of a photo a member sent to the
    `data:` address that shows it."""
    quotes = _quotes_of(transcript)
    rows: list[str] = [f'<div class="day">{escape(transcript.started_at[:10])}</div>']
    for step in transcript.steps:
        rows.extend(_rows_of(step, transcript, image_uris, quotes))
    count = len(transcript.group.get("members", []))
    group_name = str(transcript.group.get("name", ""))
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(transcript.name)}</title><style>{CHAT_CSS}</style></head><body>"
        f'<div class="phone"><div class="top"><b>{escape(group_name)}</b>'
        f"<small>{count + 1}</small></div>"
        f'<main class="talk">{"".join(rows)}</main></div></body></html>'
    )


def _rows_of(
    step: StepRecord,
    transcript: ScenarioTranscript,
    image_uris: Mapping[str, str],
    quotes: Mapping[str, str],
) -> list[str]:
    rows: list[str] = []
    shown = step.shown or {}
    kind = shown.get("type")
    if kind == "wait":
        rows.append(f'<div class="pass">{escape(str(shown.get("seconds")))} s</div>')
    elif kind in ("text", "image", "location") or (kind == "press" and shown.get("display_text")):
        rows.append(_member_row(step, shown, image_uris))
    elif kind == "press":
        label = escape(str(shown.get("label", "")))
        rows.append(
            f'<div class="system">{escape(step.sender_name or "")} pressed 「{label}」</div>'
        )
    elif kind == "open_liff":
        rows.append(_liff_row(step))
    if step.error:
        rows.append(f'<div class="system problem">⚠ {escape(step.error)}</div>')
    for output in step.outputs:
        rows.append(_bot_row(output, transcript, quotes))
    rows.append(f'<div class="meta">{escape(_meta_of(step))}</div>')
    return rows


def _member_row(step: StepRecord, shown: dict[str, Any], image_uris: Mapping[str, str]) -> str:
    name = step.sender_name or ""
    kind = shown.get("type")
    if kind == "text":
        body = f'<div class="bubble">{escape(str(shown.get("text", "")))}</div>'
    elif kind == "press":
        body = f'<div class="bubble">{escape(str(shown.get("display_text", "")))}</div>'
    elif kind == "image":
        uri = image_uris.get(str(shown.get("file")), "")
        body = f'<img class="photo" src="{escape(uri, quote=True)}" alt="">'
    else:
        body = _pin_html(shown)
    initial = escape(name[:1])
    color = AVATAR_COLORS[zlib.crc32((step.sender or "").encode()) % len(AVATAR_COLORS)]
    return (
        f'<div class="row"><div class="avatar" style="background:{color}">{initial}</div>'
        f'<div class="col"><span class="name">{escape(name)}</span>{body}</div></div>'
    )


def _liff_row(step: StepRecord) -> str:
    caption = f"{escape(step.sender_name or '')} opened the page"
    if step.note:
        caption += f" — {escape(step.note)}"
    image = f'<img src="{escape(step.screen, quote=True)}" alt="">' if step.screen else ""
    return (
        f'<div class="row"><div class="col"><div class="liff">{image}'
        f'<div class="cap">{caption}</div></div></div></div>'
    )


def _bot_row(
    output: OutputRecord, transcript: ScenarioTranscript, quotes: Mapping[str, str]
) -> str:
    numbers = action_numbers(output.messages)
    flex = FlexHtml(numbers)
    parts = [_message_html(message, flex, numbers, quotes) for message in output.messages]
    bot_name = transcript.bot_name
    label = f"{bot_name} · {output.kind} #{output.output_index}"
    if output.kind == "push" and output.target != transcript.group.get("id"):
        label += f" → {output.target[:12]} (not the group)"
    return (
        f'<div class="row bot"><div class="avatar" style="background:#4a5568">'
        f'{escape(bot_name[:1])}</div><div class="col"><span class="name">{escape(label)}</span>'
        f"{''.join(parts)}</div></div>"
    )


def _message_html(
    message: dict[str, Any], flex: FlexHtml, numbers: Mapping[int, int], quotes: Mapping[str, str]
) -> str:
    kind = message.get("type")
    if kind == "text":
        quote = quotes.get(str(message.get("quoteToken", "")))
        quoted = f'<span class="quote">{escape(quote)}</span>' if quote else ""
        body = f'<div class="bubble">{quoted}{escape(str(message.get("text", "")))}</div>'
    elif kind == "flex":
        body = f'<div title="{escape(str(message.get("altText", "")), quote=True)}">'
        body += flex.render(message.get("contents")) + "</div>"
    elif kind == "location":
        body = _pin_html(message)
    elif kind == "image" and isinstance(message.get("originalContentUrl"), str):
        body = (
            f'<img class="photo" src="{escape(message["originalContentUrl"], quote=True)}" alt="">'
        )
    else:
        body = f'<div class="bubble">[{escape(str(kind))}]</div>'
    return body + _quick_html(message.get("quickReply"), numbers)


def _quick_html(quick_reply: Any, numbers: Mapping[int, int]) -> str:
    if not isinstance(quick_reply, dict):
        return ""
    chips = []
    for item in quick_reply.get("items", []):
        action = item.get("action") if isinstance(item, dict) else None
        if isinstance(action, dict):
            number = numbers.get(id(action))
            badge = f"<sup>#{number}</sup>" if number is not None else ""
            chips.append(f'<span class="chip">{escape(str(action.get("label", "")))}{badge}</span>')
    return f'<div class="quick">{"".join(chips)}</div>' if chips else ""


def _pin_html(pin: Mapping[str, Any]) -> str:
    coordinates = f"{pin.get('latitude')}, {pin.get('longitude')}"
    return (
        '<div class="pin"><div class="map"></div><div class="text">'
        f"<b>{escape(str(pin.get('title', '')))}</b>"
        f"<small>{escape(str(pin.get('address', '')))}</small>"
        f"<small>{escape(coordinates)}</small></div></div>"
    )


def _meta_of(step: StepRecord) -> str:
    parts = [f"step {step.index}", f"{step.seconds:.1f}s"]
    if step.outputs and step.first_output_seconds is not None:
        parts.insert(1, f"first {step.first_output_seconds:.1f}s")
    elif step.kind not in ("wait", "open_liff", "press"):
        parts.append("no reply")
    if step.spend.amount:
        parts.append(f"{step.spend.amount:g} {step.spend.currency} (${step.spend.usd:.4f})")
    return " · ".join(parts)


def _quotes_of(transcript: ScenarioTranscript) -> dict[str, str]:
    """Map the quote token of each message a member sent to a short copy of what it said."""
    quotes: dict[str, str] = {}
    for step in transcript.steps:
        message = (step.event or {}).get("message") or {}
        token, text = message.get("quoteToken"), message.get("text")
        if isinstance(token, str) and isinstance(text, str):
            quotes[token] = text if len(text) <= QUOTE_MAX_CHARS else text[:QUOTE_MAX_CHARS] + "…"
    return quotes
