"""Draw a LINE Flex Message (a bubble or a carousel of bubbles) as HTML, roughly.

The shapes follow LINE's Flex layout: boxes (vertical, horizontal, baseline), text, image,
button, separator, spacer. It is an approximation to compare what the bot chose to show, not
a pixel copy of LINE. Pure; called by the chat page. Each action (button) carries its number
(see `message_actions`) so a scenario writer can name it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from html import escape
from typing import Any

SPACING_PX = {"none": 0, "xs": 2, "sm": 4, "md": 8, "lg": 12, "xl": 16, "xxl": 20}
TEXT_PX = {
    "xxs": 11,
    "xs": 13,
    "sm": 14,
    "md": 16,
    "lg": 19,
    "xl": 22,
    "xxl": 29,
    "3xl": 35,
    "4xl": 40,
    "5xl": 46,
}
BUBBLE_PX = {"nano": 120, "micro": 160, "deca": 220, "hecto": 240, "kilo": 260, "mega": 300}
DEFAULT_BUBBLE = "mega"
DEFAULT_CAROUSEL_BUBBLE = "kilo"
DEFAULT_TEXT_PX = 14
DEFAULT_PADDING_PX = 0
COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{3,8}$")
ASPECT_PATTERN = re.compile(r"^(\d{1,3}):(\d{1,3})$")


class FlexHtml:
    """Draws the Flex contents of one message; `numbers` maps an action object's `id()` to
    its number among the message's actions."""

    def __init__(self, numbers: Mapping[int, int]) -> None:
        self._numbers = numbers

    def render(self, contents: Any) -> str:
        """Return the HTML of a bubble or a carousel (an empty note when it is neither)."""
        if not isinstance(contents, dict):
            return '<div class="fx-unknown">[flex]</div>'
        if contents.get("type") == "carousel":
            bubbles = [
                self._bubble(item, DEFAULT_CAROUSEL_BUBBLE)
                for item in contents.get("contents", [])
                if isinstance(item, dict)
            ]
            return f'<div class="fx-carousel">{"".join(bubbles)}</div>'
        return self._bubble(contents, DEFAULT_BUBBLE)

    def _bubble(self, bubble: dict[str, Any], default_size: str) -> str:
        width = BUBBLE_PX.get(str(bubble.get("size")), BUBBLE_PX[default_size])
        parts = []
        for key in ("header", "hero", "body", "footer"):
            part = bubble.get(key)
            if isinstance(part, dict):
                parts.append(f'<div class="fx-part fx-{key}">{self._node(part)}</div>')
        return f'<div class="fx-bubble" style="width:{width}px">{"".join(parts)}</div>'

    def _node(self, node: dict[str, Any]) -> str:
        kind = node.get("type")
        if kind == "box":
            return self._box(node)
        if kind == "text":
            return self._text(node)
        if kind == "image":
            return self._image(node)
        if kind == "button":
            return self._button(node)
        if kind == "separator":
            return f'<div class="fx-sep"{_style(node, margin=True)}></div>'
        if kind == "spacer":
            height = SPACING_PX.get(str(node.get("size")), SPACING_PX["md"])
            return f'<div style="height:{height}px"></div>'
        if kind == "filler":
            return '<div style="flex:1"></div>'
        return f'<div class="fx-unknown">[{escape(str(kind))}]</div>'

    def _box(self, box: dict[str, Any]) -> str:
        layout = str(box.get("layout", "vertical"))
        classes = {"horizontal": "fx-box fx-row", "baseline": "fx-box fx-row fx-baseline"}
        children = []
        for child in box.get("contents", []):
            if isinstance(child, dict):
                children.append(f"<div{_child_style(child, layout)}>{self._node(child)}</div>")
        spacing = SPACING_PX.get(str(box.get("spacing")))
        gap = f";gap:{spacing}px" if spacing is not None else ""
        return (
            f'<div class="{classes.get(layout, "fx-box")}"'
            f"{_style(box, extra=gap, padding=True, background=True)}>"
            f"{''.join(children)}</div>"
        )

    def _text(self, text: dict[str, Any]) -> str:
        content = text.get("text")
        if not isinstance(content, str):
            content = "".join(
                str(span.get("text", ""))
                for span in text.get("contents", [])
                if isinstance(span, dict)
            )
        size = TEXT_PX.get(str(text.get("size")), DEFAULT_TEXT_PX)
        weight = ";font-weight:700" if text.get("weight") == "bold" else ""
        align = (
            f";text-align:{text['align']}"
            if text.get("align") in ("start", "end", "center")
            else ""
        )
        wrap = (
            ""
            if text.get("wrap") is True
            else ";white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
        )
        color = _color(text.get("color"))
        color_style = f";color:{color}" if color else ""
        return (
            f'<div class="fx-text" style="font-size:{size}px{weight}{align}{wrap}{color_style}">'
            f"{escape(content)}</div>"
        )

    def _image(self, image: dict[str, Any]) -> str:
        url = image.get("url")
        if not isinstance(url, str):
            return '<div class="fx-unknown">[image]</div>'
        match = ASPECT_PATTERN.match(str(image.get("aspectRatio", "")))
        ratio = f"{match.group(1)}/{match.group(2)}" if match else "20/13"
        fit = "cover" if image.get("aspectMode") == "cover" else "contain"
        return (
            f'<img class="fx-image" src="{escape(url, quote=True)}" alt="" loading="eager" '
            f'style="aspect-ratio:{ratio};object-fit:{fit}">{self._badge(image.get("action"))}'
        )

    def _button(self, button: dict[str, Any]) -> str:
        action = button.get("action")
        label = action.get("label", "") if isinstance(action, dict) else ""
        style = str(button.get("style", "link"))
        classes = {"primary": "fx-button fx-primary", "secondary": "fx-button fx-secondary"}
        height = ' style="padding:6px 8px"' if button.get("height") == "sm" else ""
        return (
            f'<div class="{classes.get(style, "fx-button fx-link")}"{height}>'
            f"{escape(str(label))}{self._badge(action)}</div>"
        )

    def _badge(self, action: Any) -> str:
        if not isinstance(action, dict) or id(action) not in self._numbers:
            return ""
        kind = escape(str(action.get("type", "")))
        number = self._numbers[id(action)]
        return f'<sup class="act" title="{kind} action">#{number}</sup>'


def _color(value: Any) -> str | None:
    return value if isinstance(value, str) and COLOR_PATTERN.match(value) else None


def _style(
    node: dict[str, Any],
    *,
    extra: str = "",
    margin: bool = False,
    padding: bool = False,
    background: bool = False,
) -> str:
    rules = []
    if margin and (space := SPACING_PX.get(str(node.get("margin")))) is not None:
        rules.append(f"margin-top:{space}px")
    if padding:
        pad = _padding_of(node)
        if pad:
            rules.append(pad)
    if background and (color := _color(node.get("backgroundColor"))):
        rules.append(f"background:{color}")
    style = ";".join(rules) + extra
    return f' style="{style.lstrip(";")}"' if style.strip(";") else ""


def _padding_of(node: dict[str, Any]) -> str:
    def px(key: str) -> int | None:
        value = node.get(key)
        if isinstance(value, str) and value.endswith("px") and value[:-2].isdigit():
            return int(value[:-2])
        return SPACING_PX.get(str(value))

    everywhere = px("paddingAll")
    sides = {side: px(f"padding{side}") for side in ("Top", "Bottom", "Start", "End")}
    if everywhere is None and all(value is None for value in sides.values()):
        return ""
    base = everywhere if everywhere is not None else DEFAULT_PADDING_PX
    top, bottom = sides["Top"], sides["Bottom"]
    start, end = sides["Start"], sides["End"]
    values = [base if value is None else value for value in (top, end, bottom, start)]
    return "padding:" + " ".join(f"{value}px" for value in values)


def _child_style(child: dict[str, Any], layout: str) -> str:
    rules = []
    space = SPACING_PX.get(str(child.get("margin")))
    if space is not None:
        rules.append(f"margin-{'left' if layout != 'vertical' else 'top'}:{space}px")
    flex = child.get("flex")
    if isinstance(flex, int) and not isinstance(flex, bool) and layout != "vertical":
        rules.append(f"flex:{flex}")
    return f' style="{";".join(rules)}"' if rules else ""
