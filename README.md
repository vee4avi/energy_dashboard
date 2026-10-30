# Trading dashboard

A Streamlit app with a home page and a page for each section.

- **Home:** a greeting (Singapore time), a card per section, and three calendars stacked,
  each a fixed height that scrolls inside: TradingView's macro calendar, public holidays
  (US, UK, Singapore, China) and contract expiries (Brent futures and options, from ICE).
- **CFTC positioning:** CFTC and ICE Commitments of Traders for petroleum, the desk
  commentary and EIA weekly stocks.
- **Weather & sea state:** coming soon.

```
app.py                  page setup, access code, menu
modules/
  registry.py           every section in one list (menu and home cards are built from it)
  home.py               the home page and the greeting wording
  calendars/            the home-page calendars; data/expiries.json holds the expiry dates
  cftc/                 CFTC positioning (see modules/cftc/README.md)
  weather/              placeholder
shared/                 theme, tables, commentary cards, state, secrets, access code
commentary/             the bot's weekly commentary files
ice_data/               optional ICE history files
extras/cot-report-bot/  the Telegram bot and its workflow, for reference (not run here)
tests/
```

## Contract expiries

`modules/calendars/data/expiries.json` holds ICE's published last trading days (copied from
ICE's expiry pages). To add a contract (Gasoil, Dubai, WTI…) or top up months, add an entry
with its dates in the same shape. The greeting wording lives at the top of `modules/home.py`.

## ICE data

ICE Brent, Gasoil and Dubai 1st Line come from ICE's yearly history files, downloaded
automatically (`https://www.ice.com/publicdocs/futures/COTHist2026.csv`, one per year).
Files placed in the `ice_data` folder are used first; ICE's weekly PDFs fill any week still
missing. See `ice_data/README.md`.

## EIA storage

The Storage tab needs a free key from eia.gov/opendata. Set `EIA_API_KEY` in the environment,
`.streamlit/secrets.toml` or the Community Cloud Secrets box. Without it the tab explains this
and the rest of the dashboard works as before. `COT_DEMO=1` shows synthetic stocks.

## Run it on your computer

```bash
pip install -r requirements.txt
streamlit run app.py
```

Restart it after copying new files in; a browser refresh alone often won't reload
imported modules. To open it with synthetic CFTC figures and no network:
`COT_DEMO=1 streamlit run app.py`.

Settings and secrets come from environment variables or `.streamlit/secrets.toml`
(created in the folder you start Streamlit from; it is in `.gitignore`):

| Name | What it does |
|---|---|
| `APP_PASSWORD` | Optional code for the whole app. Nothing shows until it is entered. |
| `EIA_API_KEY` | Free key from eia.gov/opendata; turns on the Storage tab. |
| `SODA_APP_TOKEN` | Optional CFTC data token, only if you hit rate limits. |

Every line sits at the top of the file with straight double quotes, for example
`EIA_API_KEY = "your-key"`, and above any `[section]` heading.

Weekly commentary needs no secret: copy the bot's `.json` files into the `commentary` folder.

## Put it on Streamlit Community Cloud

1. Create a **private** GitHub repository and upload the contents of this folder, with
   `app.py` at the repository root. Keep the `__init__.py` files and the `commentary` folder.
   Make sure `.gitignore` is uploaded too.
2. On share.streamlit.io choose New app, pick the repository, branch `main`, main file
   `app.py`. Under Advanced settings, Secrets, paste:

   ```toml
   EIA_API_KEY = "your-eia-key"
   APP_PASSWORD = "choose-something"   # or restrict viewers in the app's sharing settings
   ```
3. Each week, add the bot's new `commentary/YYYY-MM-DD.json` file to this repository's
   `commentary` folder. Pushing to GitHub redeploys the app by itself. If a change doesn't
   appear, use Reboot app in the app's menu.

Community Cloud apps are public by default, so set `APP_PASSWORD`, restrict viewers, or
both. The filesystem is wiped on every restart, so the first load afterwards is slower.

## Adding a section

1. Create `modules/<name>/__init__.py` and `modules/<name>/page.py` with a `render()` function.
2. Add a `Module(...)` line to `modules/registry.py`. The menu and the home-page card appear by themselves.

## Tests

```bash
for f in tests/test_*.py; do python "$f"; done     # or: python -m pytest tests -q
```

`COT_DEMO=1` is set by the tests themselves. Nothing in them touches the network.
