# Petroleum positioning dashboard

One Streamlit app: CFTC Commitments of Traders positioning for petroleum, the weekly desk
commentary saved by the Telegram bot, and EIA weekly US stocks (Storage tab).

```
app.py                  page setup, access code, then the CFTC page
modules/cftc/           everything for the dashboard (see modules/cftc/README.md)
shared/                 theme, tables, commentary cards, state, secrets, access code
extras/cot-report-bot/  the Telegram bot and its workflow, for reference (not run here)
tests/
```

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

## Adding a module later

The calendar module and placeholders were set aside (not deleted). When you want a second page,
restore them and use `st.navigation` again; ask and I'll wire it back in.

## Tests

```bash
for f in tests/test_*.py; do python "$f"; done     # or: python -m pytest tests -q
```

`COT_DEMO=1` is set by the tests themselves. Nothing in them touches the network.
