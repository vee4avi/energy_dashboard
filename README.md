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
| `COMMENTARY_REPO` | `owner/repo` of the bot's repository. The CFTC page reads the weekly commentary from its `commentary` folder. |
| `COMMENTARY_GITHUB_TOKEN` | Fine-grained token, Contents: Read-only on that one repository. Only for a private repository. |
| `ANTHROPIC_API_KEY` | Switches on "Analyse these dates" on the CFTC page. Leave out on a public deployment. |
| `ANALYSIS_PASSWORD` | Optional code needed before that box will run (it costs money per run). |
| `APP_PASSWORD` | Optional code for the whole app. Nothing shows until it is entered. |
| `COT_VIEW_ONLY` | Set to `"1"` on a public deployment: hides the analysis box and every setup hint. |
| `EIA_API_KEY` | Free key from eia.gov/opendata; turns on the Storage tab. |
| `SODA_APP_TOKEN` | Optional CFTC data token, only if you hit rate limits. |

Every line sits at the top of the file with straight double quotes, for example
`COMMENTARY_REPO = "your-name/cot-report-bot"`, and above any `[section]` heading.

## Put it on Streamlit Community Cloud (view-only)

One codebase serves both: the same files run on your computer with everything on, and
on Community Cloud with generation switched off.

1. Create a **private** GitHub repository and upload the contents of this folder, with
   `app.py` at the repository root. Keep the `__init__.py` files. `extras/` can stay
   or go; it is never run. Make sure `.gitignore` is uploaded too.
2. On share.streamlit.io choose New app, pick the repository, branch `main`, main file
   `app.py`. Under Advanced settings, Secrets, paste:

   ```toml
   COT_VIEW_ONLY = "1"
   COMMENTARY_REPO = "your-name/cot-report-bot"
   COMMENTARY_GITHUB_TOKEN = "github_pat_..."   # read-only, that one repository
   APP_PASSWORD = "choose-something"            # or restrict viewers in the app's sharing settings
   ```
3. Pushing to GitHub redeploys the app by itself. If a change doesn't appear, use
   Reboot app in the app's menu.

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
