"""Draw the front page of a run: every scenario in a row with its steps, seconds, spend and
the number of steps that went wrong, linking to its chat page and transcript.

Pure; called by the report writer. The page loads nothing from outside.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from line_group_agent.simulator.transcript import ScenarioTranscript

INDEX_CSS = """
body { margin: 0; padding: 24px 16px; background: #f5f6f8; color: #14161a;
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif; }
main { max-width: 960px; margin: 0 auto; }
h1 { font-size: 20px; margin: 0 0 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.card { background: #fff; border: 1px solid #dfe2e7; border-radius: 12px; padding: 12px; }
.card h2 { font-size: 16px; margin: 0 0 6px; }
.card img { width: 100%; max-height: 360px; object-fit: cover; object-position: top;
  border-radius: 8px; border: 1px solid #e6e8ec; }
.facts { color: #4a4e54; font-size: 13px; margin: 0 0 8px; }
.bad { color: #b3261e; font-weight: 600; }
a { color: #1a5fd0; }
"""


def render_index_page(transcripts: Sequence[ScenarioTranscript]) -> str:
    """Return the front page for these runs."""
    total_usd = sum(t.total_spend.usd for t in transcripts if t.total_spend)
    cards = "".join(_card_of(transcript) for transcript in transcripts)
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Simulated LINE runs</title><style>{INDEX_CSS}</style></head><body><main>"
        f"<h1>{len(transcripts)} scenarios · ${total_usd:.4f} in all</h1>"
        f'<div class="grid">{cards}</div></main></body></html>'
    )


def _card_of(transcript: ScenarioTranscript) -> str:
    slug = escape(transcript.slug, quote=True)
    spend = transcript.total_spend
    cost = f"${spend.usd:.4f}" if spend else "—"
    problems = (
        f' · <span class="bad">{transcript.error_count} step(s) with a problem</span>'
        if transcript.error_count
        else ""
    )
    stopped = (
        f'<div class="facts bad">{escape(transcript.stopped_reason)}</div>'
        if transcript.stopped_reason
        else ""
    )
    return (
        f'<section class="card"><h2>{escape(transcript.name)}</h2>'
        f'<p class="facts">{len(transcript.steps)} steps · {transcript.total_seconds:.1f}s · '
        f"{cost}{problems}</p>{stopped}"
        f'<a href="{slug}/chat.html"><img src="{slug}/screens/chat.png" alt="" '
        f"onerror=\"this.style.display='none'\"></a>"
        f'<p class="facts"><a href="{slug}/chat.html">chat</a> · '
        f'<a href="{slug}/transcript.json">transcript</a></p></section>'
    )
