"""The styles of the chat page, kept apart from the code that builds the page.

Plain text; read by `chat_page`. No external font or file is loaded.
"""

CHAT_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0; background: #7d96bd; color: #111;
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif;
}
.phone { width: 390px; min-height: 100vh; margin: 0 auto; background: #8aa3c9; }
.top { position: sticky; top: 0; z-index: 2; padding: 10px 14px; background: #f4f5f7;
  border-bottom: 1px solid #d5d8de; }
.top b { font-size: 16px; }
.top small { color: #667; margin-left: 6px; }
.talk { padding: 10px 10px 40px; display: flex; flex-direction: column; gap: 8px; }
.day, .pass, .system { align-self: center; color: #fff; background: rgba(60, 80, 110, .45);
  border-radius: 10px; padding: 2px 10px; font-size: 11px; max-width: 90%; text-align: center; }
.system.problem { background: #b3261e; }
.row { display: flex; gap: 6px; align-items: flex-start; max-width: 100%; }
.row.bot { flex-direction: row-reverse; }
.avatar { flex: none; width: 34px; height: 34px; border-radius: 50%; color: #fff;
  display: flex; align-items: center; justify-content: center; font-weight: 700; }
.col { display: flex; flex-direction: column; gap: 4px; min-width: 0; max-width: 300px; }
.row.bot .col { align-items: flex-end; }
.name { font-size: 11px; color: #fff; }
.bubble { padding: 7px 11px; border-radius: 16px; background: #fff; white-space: pre-wrap;
  overflow-wrap: anywhere; }
.bot .bubble { background: #8de055; }
.quote { display: block; font-size: 11px; color: #555; border-left: 3px solid #0006;
  padding-left: 6px; margin-bottom: 4px; white-space: normal; }
.photo { max-width: 220px; border-radius: 12px; display: block; }
.photo.plan { max-width: 300px; }
.pin, .liff { background: #fff; border-radius: 12px; overflow: hidden; width: 240px; }
.pin .map { height: 90px; background: repeating-linear-gradient(45deg, #dfe8d6, #dfe8d6 10px,
  #cfdcc4 10px, #cfdcc4 20px); }
.pin .text { padding: 8px 10px; }
.pin small { color: #666; display: block; }
.sticker { background: #fff8; border: 2px dashed #fffa; border-radius: 12px; padding: 14px 18px;
  text-align: center; }
.sticker b { display: block; }
.sticker small { color: #fff; display: block; }
.mention { color: #1a73e8; font-weight: 700; }
.liff img { width: 100%; max-height: 460px; object-fit: cover; object-position: top;
  display: block; }
.liff .cap { padding: 6px 10px; font-size: 12px; color: #555; }
.meta { align-self: flex-end; font-size: 11px; color: #fffd; }
.quick { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.chip { background: #fff; border: 1px solid #06c755; color: #06a047; border-radius: 16px;
  padding: 3px 11px; font-size: 13px; }
.chip sup, .act { color: #889; font-size: 9px; margin-left: 3px; font-weight: 400; }
.fx-carousel { display: flex; gap: 8px; overflow-x: auto; max-width: 340px; padding-bottom: 4px; }
.fx-bubble { background: #fff; border-radius: 14px; overflow: hidden; flex: none; }
.fx-part { min-width: 0; }
.fx-body > .fx-box, .fx-header > .fx-box, .fx-footer > .fx-box { padding: 12px; }
.fx-box { display: flex; flex-direction: column; min-width: 0; }
.fx-row { flex-direction: row; }
.fx-baseline { align-items: baseline; }
.fx-text { overflow-wrap: anywhere; }
.fx-image { width: 100%; display: block; background: #e6e8ec; }
.fx-sep { height: 1px; background: #e2e4e8; }
.fx-button { text-align: center; padding: 10px 8px; border-radius: 8px; }
.fx-primary { background: #06c755; color: #fff; font-weight: 700; }
.fx-primary .act { color: #d6f5e1; }
.fx-secondary { background: #e9ebef; font-weight: 700; }
.fx-link { color: #1a73e8; }
.fx-unknown { color: #999; font-size: 12px; }
"""
