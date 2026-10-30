"""The greeting panel: the greeting on the left, live world clocks on the right.

The clocks tick in the browser, so the panel is its own small HTML page (shown in an
iframe); Streamlit's Markdown cannot run scripts. NASDAQ's open/closed badge uses
New York time and the NYSE holiday list, which NASDAQ shares.
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import json
from pathlib import Path

from shared import theme

PANEL_HEIGHT = 186  # px
# The clock digits: DSEG7 Classic, a seven-segment LED font like the clocks on a trading
# floor (SIL Open Font Licence, see assets/DSEG-LICENSE.txt). It is 5 KB, so it is built
# into the page rather than fetched.
DIGITS_FILE = Path(__file__).parent / "assets" / "DSEG7Classic-Bold.woff2"
LED_COLOUR = "#1b1f18"  # the digits; e.g. red "#ff3b2f" or amber "#ffb000" for an LED look


def _digits_font_face() -> str:
    try:
        data = base64.b64encode(DIGITS_FILE.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"@font-face {{ font-family: 'DSEG7'; src: url(data:font/woff2;base64,{data}) format('woff2'); }}"

# (label, IANA time zone, market shown under the clock, sessions in local time)
CLOCKS = (
    ("Singapore", "Asia/Singapore", "", None),
    ("London", "Europe/London", "", None),
    ("New York", "America/New_York", "NASDAQ", {"pre": "04:00", "open": "09:30", "close": "16:00", "post": "20:00"}),
)


def _us_market_holidays(today: dt.date) -> list[str]:
    try:
        import holidays

        days = holidays.financial_holidays("NYSE", years=[today.year, today.year + 1])
        return sorted(d.isoformat() for d in days)
    except Exception:  # noqa: BLE001 - the badge just ignores holidays then
        return []


def panel_html(headline: str, aside: str, now: dt.datetime) -> str:
    font = theme.GREETING_FONT
    clocks = "".join(
        f'<div class="clock" data-tz="{tz}" data-market="{market}">'
        f'<div class="date">&nbsp;</div><div class="led time">88:88:88</div>'
        f'<div class="city">{html.escape(label)}</div><div class="badge"></div></div>'
        for label, tz, market, _ in CLOCKS
    )
    sessions = {market: hours for _, _, market, hours in CLOCKS if market}
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family={font.replace(' ', '+')}:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>
{_digits_font_face()}
html, body {{ margin: 0; padding: 0; background: transparent; }}
.panel {{ box-sizing: border-box; height: {PANEL_HEIGHT - 6}px; display: flex; align-items: center;
  justify-content: space-between; gap: 2rem; padding: 0 2rem 0 1.8rem; border-radius: 10px;
  background: linear-gradient(120deg, #d9e1c6 0%, #cbd5b0 100%); border-left: 6px solid #6f7d4a;
  font-family: 'Source Sans 3', 'Segoe UI', sans-serif; }}
.head {{ font-family: '{font}', Georgia, serif; font-size: 32px; font-weight: 500; color: #2f3a22;
  line-height: 1.2; letter-spacing: -0.01em; }}
.aside {{ font-family: '{font}', Georgia, serif; font-size: 18px; font-style: italic; color: #4f5c33; margin-top: .4rem; }}
.stamp {{ font-size: 13px; color: #5f6655; margin-top: .6rem; }}
.clocks {{ display: flex; gap: .8rem; }}
.clock {{ min-width: 172px; background: rgba(255,255,255,.55); border: 1px solid rgba(79,92,51,.25);
  border-radius: 10px; padding: .6rem 1rem .55rem 1rem; display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-align: center; }}
.date {{ font-size: 12px; color: #5f6655; }}
.led {{ margin: .2rem 0 .3rem 0; white-space: nowrap; }}
/* Each character sits in its own cell over a faint "8" (its unlit segments), so the digits
   line up like a real seven-segment display whatever the time. */
.cell {{ position: relative; display: inline-block; font-family: 'DSEG7', 'Courier New', monospace;
  font-size: 24px; line-height: 1.2; }}
.cell .g {{ color: {LED_COLOUR}; opacity: .08; }}
.cell .v {{ position: absolute; right: 0; top: 0; color: {LED_COLOUR}; }}
.city {{ font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: #4f5c33; }}
.badge:empty {{ display: none; }}
.badge {{ margin-top: .2rem; font-size: 12px; font-weight: 700; color: #000; }}
@media (max-width: 900px) {{ .clocks {{ display: none; }} }}
</style></head><body>
<div class="panel">
  <div><div class="head">{html.escape(headline)}</div><div class="aside">{html.escape(aside)}</div>
  <div class="stamp">{now:%A %d %B %Y}</div></div>
  <div class="clocks">{clocks}</div>
</div>
<script>
const SESSIONS = {json.dumps(sessions)};
const HOLIDAYS = new Set({json.dumps(_us_market_holidays(now.date()))});
function parts(tz, d) {{
  const f = new Intl.DateTimeFormat('en-GB', {{timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit',
    weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour12: false}});
  const o = {{}}; f.formatToParts(d).forEach(p => o[p.type] = p.value); return o;
}}
function status(market, p, iso) {{
  const s = SESSIONS[market]; if (!s) return ['', ''];
  if (['Sat', 'Sun'].includes(p.weekday) || HOLIDAYS.has(iso)) return ['Closed', ''];
  const hm = p.hour + ':' + p.minute;
  if (hm >= s.open && hm < s.close) return ['Open', 'open'];
  if (hm >= s.pre && hm < s.open) return ['Pre-market', 'ext'];
  if (hm >= s.close && hm < s.post) return ['After hours', 'ext'];
  return ['Closed', ''];
}}
const MONTHS = {{Jan:'01',Feb:'02',Mar:'03',Apr:'04',May:'05',Jun:'06',Jul:'07',Aug:'08',Sep:'09',Oct:'10',Nov:'11',Dec:'12'}};
function tick() {{
  const now = new Date();
  document.querySelectorAll('.clock').forEach(el => {{
    const p = parts(el.dataset.tz, now);
    const text = p.hour + ':' + p.minute + ':' + p.second;
    el.querySelector('.time').innerHTML = [...text].map(c =>
      '<span class="cell"><span class="g">' + (c === ':' ? ':' : '8') + '</span><span class="v">' + c + '</span></span>'
    ).join('');
    el.querySelector('.date').textContent = p.weekday + ' ' + p.day + ' ' + p.month;
    const market = el.dataset.market;
    if (market) {{
      const [text] = status(market, p, p.year + '-' + MONTHS[p.month] + '-' + p.day);
      const b = el.querySelector('.badge'); b.textContent = market + ' · ' + text;
    }}
  }});
}}
tick(); setInterval(tick, 1000);
</script></body></html>"""
