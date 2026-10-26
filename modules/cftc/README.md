# CFTC positioning module

Streamlit pages over the CFTC Commitments of Traders data for petroleum contracts:
crude, gasoline, distillate, gasoil and anything else the CFTC files under
*Petroleum and products*, plus ICE Futures Europe. It is the first module of the
energy dashboard; see the README at the top of the project for running and deploying.

To open it without network access (synthetic figures, same shapes), start the app with
`COT_DEMO=1`. If you hit Socrata rate limits, get a free app token from
publicreporting.cftc.gov and set `SODA_APP_TOKEN`.

## What's in it

The sidebar drives everything: report family, basis, product group, products,
trader categories, units (contracts or % of open interest) and how much history
to pull.

**Data source** (CFTC / ICE) filters by where the numbers come from. ICE-sourced
contracts carry ` (ICE)` after the name; CFTC-sourced ones keep the plain name,
even if the contract trades on an ICE venue. Leave it empty for both.

**Product group** (Crude / Products / Spreads / Other) narrows the product list,
so "show me the crack spreads" is one click. Groups are assigned by rules on the
contract name — `GROUP_RULES` in `config/settings.py` — and any contract that
lands in the wrong place can be pinned with `GROUP_OVERRIDES` (by contract code).
Leave the chips empty to see everything.

**Colours.** Table cells shade by size only: light grey near zero, deepening to
blue for the largest numbers, with the sign carried by the number. On Snapshot
the two net-position tables share one scale, so equal numbers get equal shades.

**Basis** has three settings. *Futures only* and *futures + options combined* are
what the CFTC publishes. *Options only (implied)* is derived — combined minus
futures-only — because no exchange publishes an options-only COT. The CFTC
delta-adjusts options into futures equivalents before folding them into the
combined report, so the implied options figures are delta-weighted exposures,
not option contract counts. They still answer the useful question: how much of
the week's positioning change happened in options rather than outright futures.

**ICE Futures Europe** (ICE Brent, ICE Gasoil) is included by default alongside
the CFTC contracts. ICE publishes its COT free but as weekly PDFs rather than an
API, so `sources/ice.py` fetches and parses them. Each PDF carries five weeks of
history, so a three-year backfill is about thirty fetches, and every parsed file
is cached to `.cache/ice/` — later runs only fetch what is new. ICE uses the
CFTC's disaggregated categories, so its rows merge into the same frame and every
filter and chart treats them identically. ICE publishes no legacy-format report,
so the toggle disappears when you switch to legacy.

| Tab | What it answers |
|---|---|
| **Snapshot** | The report date, the comparison date and the change between them, stacked, each split into Long / Short / Net under every trader category. A toggle switches the headline numbers between participants. Baseline: last week, 4w, 13w, 1y or any date. Desk commentary sits to the right (see below). Plus COT index and z-score. |
| **Compare dates** | Any number of report dates side by side, as levels, changes, or both. Changes measured week-to-week or against the oldest selected date. |
| **Full table** | Every week of history for one product in one scrolling table, as in a spreadsheet: for each trader category Long / Short / Net and their week-on-week changes (green up, red down), then open interest. Pick the product, the trader categories (other reportable, non-reportable and total can be added), the window, and whether to show changes. CSV download. |
| **Breakdown** | Long / short / spread detail for one product on one date. |
| **Data** | The tidy frame behind all of it, a CSV download, and a **Contract coverage** panel listing every contract found, its group, and how it was found. |

Derived fields: `net`, `net_pct_oi`, changes over 1/4/13/26/52 weeks, a rolling
z-score, and the Williams-style COT index (0 = window low, 100 = window high).
The window is set in the sidebar and defaults to 156 weeks.

## Commentary

**Saved weekly commentary.** The Telegram bot (`extras/cot-report-bot/cot_report_bot.py`) writes each
week's commentary to `commentary/YYYY-MM-DD.json`: the text, the news it used, the
numbers it was shown, and the pair of dates it describes (the report date and the
week before). The Snapshot tab shows it beside the tables **only** when the two
dates being compared are exactly that pair. Any other comparison shows nothing,
with a one-line hint if commentary exists for the report date. The bot analyses the
disaggregated report on a futures + options (combined) basis, so the panel says so
when you are viewing a different basis. History starts from the first run that saves.

**Where it comes from.** The dashboard reads the commentary from the `commentary` folder of the
bot's GitHub repository, and from nowhere else. Set `COMMENTARY_REPO` to the repository
(`owner/repository`). It looks again every ten minutes and when you press Refresh data,
and downloads each weekly file only once. If GitHub cannot be reached, or
`COMMENTARY_REPO` is missing, the page shows a note saying so. Settings come from the
environment or Streamlit secrets:

```toml
COMMENTARY_REPO = "your-name/cot-report-bot"
# Optional:
COMMENTARY_BRANCH = "main"                 # default
COMMENTARY_FOLDER = "commentary"           # default
COMMENTARY_GITHUB_TOKEN = "github_pat_..." # only for a private repository
```

For a private repository, create a fine-grained token limited to that one repository
with Contents: Read-only, and keep it in `.streamlit/secrets.toml` (already in
`.gitignore`). A public repository needs no token.

**Analyse these dates.** With `ANTHROPIC_API_KEY` set, a box under the commentary runs
a new analysis for the dates and products on screen, using the dashboard's own
numbers (net, changes, COT index, z-score). An optional dated news search is offered
up to eight weeks. It costs about $0.02 a run, or $0.08 to $0.15 with news. The key
and an optional `ANALYSIS_PASSWORD` come from the environment or Streamlit secrets:

```toml
# .streamlit/secrets.toml  (locally), or the app's Secrets box on Community Cloud
ANTHROPIC_API_KEY = "sk-ant-..."
ANALYSIS_PASSWORD = "choose-something"   # recommended on any public link
```

Each browser session may start ten new analyses, identical requests are served from
a cache for free, and every result shows its token use and estimated cost. Set a
monthly spend limit on the key in the Anthropic Console as well. Prices live in
`MODEL_PRICES` in `modules/cftc/config/settings.py`; update them when Anthropic's change.

## The weekly bot

The Telegram bot lives in its own repository and runs on GitHub Actions. Its script
and workflow are kept here for reference in `extras/cot-report-bot/`. Do not copy the
workflow into this repository: it is written for the bot's repository, where the script
sits at the top level. The bot needs three repository secrets (`TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`); no GitHub token, because the workflow pushes
with its own. Every Friday at 20:30 UTC it sends the messages, saves the commentary
and commits it. A holiday week, when the CFTC publishes late, is skipped automatically
on the schedule; a manual Run workflow always runs.

## Reading the numbers

**Net** is long minus short. Net and every change carry an explicit `+` or `-`;
Long and Short are plain counts, since they cannot be negative.

**COT index** shows where this week's net position sits between its lowest (0)
and highest (100) over the lookback window (default 156 weeks, adjustable in the
sidebar): 0 is the most net short it has been in the window, 100 the most net
long. **Z-score** is how many standard deviations net is from its window average.
Above roughly 80 or below 20 is conventionally called extreme; that is a rule of
thumb, not a threshold with any special meaning. Both depend on the window, so
widening it changes the reading. For producers and swap dealers (hedgers) a high
reading usually means they are net long relative to their own history, not that
they are bullish.

**Legacy vs disaggregated.** Legacy splits traders into *commercial* (anyone
using futures to hedge a business risk), *non-commercial* (large speculators) and
*non-reportable*. Because it classifies by purpose, swap dealers fall inside
commercial and funds inside non-commercial, so neither group is clean.
Disaggregated (from mid-2006) separates producer/merchant, swap dealers, managed
money and other reportables, which is why it is the standard for energy. Legacy
is worth keeping only for history before 2006 or to match commentary that quotes
"non-commercial net length". ICE publishes no legacy report.

## Layout

```
modules/cftc/
  page.py            the page: header, sidebar filters, tabs
  services.py        cached loaders (the only place caching touches data)
  config/settings.py dataset ids, trader categories, universe + group rules, defaults
  sources/           cftc.py (Socrata), ice.py (PDF reports), commentary.py (GitHub),
                     llm.py (on-demand analysis), demo.py (synthetic data)
  analytics/         cot.py (net, changes, z-scores, COT index), narrative.py (prompts)
  ui/                filters.py (sidebar), views.py (the tabs)
shared/              theme, long/short/net tables, commentary cards, state, secrets, access code
```

The tidy frame every layer speaks is one row per **report date × contract ×
trader category**, with `long`, `short`, `spread`, `open_interest`, `product`.

## Next up: prices

The plan is positioning-vs-price overlays and correlations. The join is the
awkward part and worth settling before writing code: COT dates are Tuesdays,
prices are daily, so `report_date` needs an as-of join onto the Tuesday settle
(or a weekly resample), and comparing net positioning to price levels is usually
less informative than comparing *changes* — weekly net change against weekly
return, and rolling correlations of those. Which price source you use decides
the rest: an EIA/FRED series is free but daily-settle only, while a terminal
export gives the specific contract months that actually match each COT contract.

## Things worth knowing about the data

- Positions are as of **Tuesday close**, published **Friday 15:30 ET**. The
  dashboard shows the next publication date in the header.
- The CFTC's Socrata column names are inconsistent (`swap__positions_short_all`
  really does have two underscores, `_all` suffixes come and go). `sources/cftc.py`
  resolves them by pattern from the live column list instead of hard-coding, and
  `tests/test_cftc_parsing.py` pins that behaviour.
- Products are discovered at runtime, so new contracts appear without a code
  change. The universe is the CFTC's *Petroleum and products* subgroup **plus**
  oil-named contracts filed under other subgroups (crack, WTI, Brent, WCS, RBOB,
  ULSD, jet, heating oil, fuel oil, gasoil, diesel, naphtha — `SWEEP_KEYWORDS`).
  Nothing is hidden for being thin, and a contract stays listed if it reported
  in the last eight weeks, so one skipped week doesn't make it vanish. Open the
  Data tab's **Contract coverage** panel to see exactly what was found.
- Product labels come straight from the CFTC's contract name (tidied to title
  case, acronyms kept), so two different contracts can never share a label. To
  rename one, add its exact upper-case name to `PRODUCT_NAME_OVERRIDES`.
- ICE's reports are filed to ICE, not the CFTC, and its reporting thresholds are
  the CFTC's (350 lots for Brent, 250 for gasoil) applied to ICE's own books.
  Treat ICE Brent and CFTC WTI as comparable in shape, not in construction.
- ICE's PDF file names use the Tuesday market date (`BrentFut_16092026.pdf`) and
  live under two paths — `/publicdocs/cot_report/automated/` for recent reports
  and `/publicdocs/cot_report/` for older ones. The reader tries both.
- To add another ICE contract, add its file stem to `PRODUCTS` in `sources/ice.py`.
- Combined (futures + options) positions are delta-adjusted by the CFTC; levels
  are not comparable with futures-only.

## Tests

```bash
python tests/test_cftc_parsing.py     # CFTC column resolution and tidying
python tests/test_ice_parsing.py      # ICE PDF layout, pinned to real reports
python tests/test_tables.py           # long/short/net tables, source tagging
python tests/test_analysis.py         # saved commentary, prompts, cost, the Snapshot panel
python tests/test_notes.py            # commentary cards, table widths, Full table, Compare breakdown
python tests/test_app.py              # router, home page, access code, filters kept between pages
# or: python -m pytest tests -q
```

The ICE tests are worth a word: the fixtures are the real text of two published
ICE reports, and the mapping of the fourteen unlabelled columns to trader
categories is checked by reconciling every leg against the percentage-of-open-
interest table ICE prints in the same PDF. If ICE reorders a column, that test
fails rather than the dashboard quietly showing swap dealers as managed money.
