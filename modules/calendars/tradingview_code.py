"""Paste TradingView widget code here.

On TradingView's widget pages, set a widget up the way you like and copy the embed code it
gives you. Paste it between the triple quotes below, replacing what is there, keeping the
three quote marks at each end. Nothing else needs changing.

Leave MACRO_CALENDAR_CODE empty to keep the built-in macro calendar (all countries, all
importance levels). Change the heights if a widget looks cut off or has spare room.
"""

# Market summary (the strip above the calendars).
MARKET_SUMMARY_CODE = r"""
<script type="module" src="https://widgets.tradingview-widget.com/w/en/tv-market-summary.js"></script>
<tv-market-summary></tv-market-summary>
"""
MARKET_SUMMARY_HEIGHT = 255  # px

# Macro (economic) calendar. Empty = built-in version.
MACRO_CALENDAR_CODE = r"""
"""
MACRO_CALENDAR_HEIGHT = 733  # px, used only for pasted code
