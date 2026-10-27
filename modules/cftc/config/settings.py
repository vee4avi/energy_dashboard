"""Configuration for the COT dashboard.

Everything that is likely to change (dataset ids, trader categories, product
naming, defaults) lives here so the rest of the app stays generic. When the
project grows to prices / EIA storage, add their settings alongside these.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Socrata / CFTC Public Reporting Environment
# --------------------------------------------------------------------------
SODA_DOMAIN = "publicreporting.cftc.gov"

# (report family, basis) -> Socrata resource id
DATASETS: dict[tuple[str, str], str] = {
    ("disaggregated", "futures_only"): "72hh-3qpy",
    ("disaggregated", "combined"): "kh3c-gbw2",
    ("legacy", "futures_only"): "6dca-aqww",
    ("legacy", "combined"): "jun7-fc8e",
    ("tff", "futures_only"): "gpe5-46if",
    ("tff", "combined"): "yw9f-hn96",
}

REPORT_LABELS = {
    "disaggregated": "Disaggregated (Producer / Swap / Managed money)",
    "legacy": "Legacy (Commercial / Non-commercial)",
}
BASIS_LABELS = {
    "futures_only": "Futures only",
    "combined": "Futures + options combined",
    "options_implied": "Options only (implied)",
}

# "Options only" is not published anywhere: it is combined minus futures-only,
# which leaves the delta-adjusted options exposure the CFTC folds into the
# combined report. Levels are futures-equivalents, not option contracts.
IMPLIED_OPTIONS_BASIS = "options_implied"
IMPLIED_OPTIONS_NOTE = (
    "Options figures are derived: futures+options combined minus futures-only. "
    "The CFTC delta-adjusts options into futures equivalents, so these are "
    "delta-weighted exposures rather than option contract counts."
)

# Socrata caps a single response at 50k rows.
PAGE_SIZE = 50_000
REQUEST_TIMEOUT = 60
CACHE_TTL_SECONDS = 60 * 60 * 6  # COT is weekly; 6h keeps it fresh enough

# --------------------------------------------------------------------------
# Analysis (saved weekly commentary + optional on-demand runs)
# --------------------------------------------------------------------------
# The bot saves one JSON file per report date. Copy them into the "commentary"
# folder next to app.py; the dashboard reads that folder and nothing else.
COMMENTARY_REPORT = "disaggregated"  # the bot only analyses this report family
COMMENTARY_MAX_FILES = 104  # how many of the newest weekly files to read
ANALYSIS_COST_HINT = {
    "plain": "about $0.02",
    "news": "about $0.08 to $0.15",
}


# --------------------------------------------------------------------------
# Product universe
# --------------------------------------------------------------------------
# Preferred filter: the CFTC's own commodity subgroup.
PETROLEUM_SUBGROUP = "PETROLEUM AND PRODUCTS"

# Oil-named contracts that the CFTC files under another subgroup are pulled in
# as well. The sweep runs on the market name, so crack spreads, jet / heating
# oil spreads and crude differentials are not lost to a subgroup quirk.
SWEEP_KEYWORDS = (
    "CRACK",
    "CRUDE OIL",
    "BRENT",
    "WTI",
    "WCS",
    "RBOB",
    "ULSD",
    "GASOLINE",
    "GASOIL",
    "GAS OIL",
    "FUEL OIL",
    "HSFO",
    "LSFO",
    "BUNKER",
    "HEATING OIL",
    "HEAT OIL",
    "JET FUEL",
    "JET ",
    "DIESEL",
    "NAPHTHA",
)

# The sweep never looks inside these subgroups: names there contain oil words
# without being oil (soybean oil, power "heat rate", emissions, ...).
SWEEP_EXCLUDED_SUBGROUPS = (
    "ELECTRICITY AND SOURCES",
    "EMISSIONS",
    "GRAINS",
    "OILSEED and PRODUCTS",
    "LIVESTOCK/MEAT PRODUCTS",
    "DAIRY PRODUCTS",
    "FOODSTUFFS/SOFTS",
    "PRECIOUS METALS",
    "BASE METALS",
    "WOOD PRODUCTS",
    "FERTILIZER",
    "CHEMICALS",
    "FIBER",
)

# A contract stays in the list if it reported at any point in this window, so
# one skipped week does not make it vanish from the product filter.
CONTRACT_LOOKBACK_WEEKS = 8

# Labels come from the CFTC's own contract name, so two different contracts can
# never collapse into one label. Add an exact (upper-case) contract name here
# only if you want a friendlier label for it.
PRODUCT_NAME_OVERRIDES: dict[str, str] = {}

# Friendlier labels matched by pattern. Each rule is (regex, label); the regex is
# searched in the CFTC's full upper-case market name, which includes the exchange
# ("... - NEW YORK MERCANTILE EXCHANGE"), so the same product on two exchanges can
# get two labels. First match wins. Anything that matches no rule keeps the
# label built from the CFTC's own contract name.
_NYMEX = r"NEW YORK MERCANTILE|NYMEX"
_ICE = r"\bICE\b"
PRODUCT_NAME_RULES: tuple[tuple[str, str], ...] = (
    (rf"^WTI FINANCIAL\b.*(?:{_NYMEX})", "WTI Nymex"),
    (rf"^WTI-PHYSICAL\b.*(?:{_NYMEX})", "WTI Physical Nymex"),
    (rf"LIGHT SWEET.*\bWTI\b.*{_ICE}", "WTI Ice EU"),
    (rf"^WTI\b(?!-PHYSICAL|\s+FINANCIAL).*\b1ST LINE\b.*{_ICE}", "WTI 1st line Ice Futures"),
    (rf"^BRENT\b.*\bLAST DAY\b.*(?:{_NYMEX})", "Brent Last Day Nymex"),
)

# Words that stay upper case when a contract name is tidied to title case.
ACRONYMS = (
    "WTI", "RBOB", "ULSD", "NY", "NYH", "NYMEX", "ICE", "WCS", "LLS", "US",
    "USD", "UK", "LD", "MT", "CIF", "FOB", "ARA", "NWE", "MOPS", "HSFO",
    "LSFO", "LSGO", "FO", "TC", "TD", "RIN", "D4", "D6",
)

# How many contracts to pre-select on first load (ranked by open interest).
DEFAULT_PRODUCT_COUNT = 4


# --------------------------------------------------------------------------
# Product groups (the "Crude / Products / Spreads" filter)
# --------------------------------------------------------------------------
# Rules run top to bottom on the contract name (the part before the exchange);
# the first match wins, so spreads are caught before their crude / product legs.
GROUP_ORDER = ("Crude", "Products", "Spreads", "Other")

GROUP_RULES: tuple[tuple[str, str], ...] = (
    (
        "Spreads",
        r"CRACK|\bSPR\b|SPREAD|/|\bVS\.?(?:\s|$)|\bVERSUS\b|\bDIFF|BASIS|\bARB\b",
    ),
    (
        "Crude",
        r"CRUDE|\bWTI|BRENT|\bWCS\b|\bMARS\b|\bLLS\b|DUBAI|\bOMAN\b|URALS|"
        r"\bMIDLAND\b|\bSWEET\b|\bSOUR\b",
    ),
    (
        "Products",
        r"GASOLINE|RBOB|ULSD|HEAT|DIESEL|\bJET\b|GASOIL|GAS OIL|FUEL OIL|NAPHTHA|"
        r"PROPANE|KEROSENE|BUTANE|\bETHANE\b|"
        # Fuel-oil family under its trade abbreviations (USGC HSFO, VLSFO, ...).
        r"\b(?:HS|LS|VLS)FO\b|\bFUEL\b|BUNKER|MARINE",
    ),
)

# Pin a contract to a group by its CFTC contract code if a rule gets one wrong.
GROUP_OVERRIDES: dict[str, str] = {}


def contract_part(market_name: str) -> str:
    """The contract name without its trailing ' - EXCHANGE'."""
    return (market_name or "").rsplit(" - ", 1)[0].strip()


def classify_product(market_name: str, code: str | None = None) -> str:
    """Crude / Products / Spreads / Other for one contract."""
    import re

    if code and code in GROUP_OVERRIDES:
        return GROUP_OVERRIDES[code]
    name = contract_part(market_name).upper()
    for group, pattern in GROUP_RULES:
        if re.search(pattern, name):
            return group
    return "Other"


# --------------------------------------------------------------------------
# ICE Futures Europe
# --------------------------------------------------------------------------
# ICE publishes its own COT for Brent and Gasoil (free, weekly PDFs). It uses
# the CFTC's disaggregated categories, so ICE rows merge into the same frame.
INCLUDE_ICE_BY_DEFAULT = True
ICE_ONLY_REPORT = "disaggregated"  # ICE publishes no legacy-format report

# Where a contract's numbers come from. ICE-sourced contracts carry an " (ICE)"
# suffix on their name; CFTC-sourced ones keep the plain name.
SOURCE_OPTIONS = ("CFTC", "ICE")
ICE_SUFFIX = " (ICE)"


# --------------------------------------------------------------------------
# Trader categories
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Category:
    key: str  # internal id
    label: str  # shown in the UI
    prefix: str  # regex prefix used to find the raw Socrata columns
    report: str  # which report family it belongs to
    short_label: str = ""
    description: str = ""
    has_spread: bool = True

    @property
    def ui_label(self) -> str:
        return self.short_label or self.label


DISAGGREGATED_CATEGORIES: tuple[Category, ...] = (
    Category(
        key="m_money",
        label="Managed money",
        short_label="Managed money",
        prefix=r"m_money_positions",
        report="disaggregated",
        description="Funds and CTAs — the speculative flow most traders watch.",
    ),
    Category(
        key="prod_merc",
        label="Producer / merchant / processor / user",
        short_label="Producer/merchant",
        prefix=r"prod_merc_positions",
        report="disaggregated",
        has_spread=False,
        description="Physical hedgers: producers, refiners, airlines, end users.",
    ),
    Category(
        key="swap",
        label="Swap dealers",
        short_label="Swap dealers",
        prefix=r"swap_+positions",
        report="disaggregated",
        description="Banks and dealers hedging OTC swap books.",
    ),
    Category(
        key="other_rept",
        label="Other reportables",
        short_label="Other reportable",
        prefix=r"other_rept_positions",
        report="disaggregated",
        description="Large traders that fit none of the other buckets.",
    ),
    Category(
        key="nonrept",
        label="Non-reportable (small traders)",
        short_label="Non-reportable",
        prefix=r"nonrept_positions",
        report="disaggregated",
        has_spread=False,
        description="Positions below CFTC reporting thresholds.",
    ),
    Category(
        key="tot_rept",
        label="Total reportable",
        short_label="Total reportable",
        prefix=r"tot_rept_positions",
        report="disaggregated",
        description="Sum of all reportable categories.",
    ),
)

LEGACY_CATEGORIES: tuple[Category, ...] = (
    Category(
        key="noncomm",
        label="Non-commercial",
        short_label="Non-commercial",
        prefix=r"noncomm_positions",
        report="legacy",
        description="Speculators under the legacy classification.",
    ),
    Category(
        key="comm",
        label="Commercial",
        short_label="Commercial",
        prefix=r"comm_positions",
        report="legacy",
        has_spread=False,
        description="Hedgers under the legacy classification.",
    ),
    Category(
        key="nonrept",
        label="Non-reportable (small traders)",
        short_label="Non-reportable",
        prefix=r"nonrept_positions",
        report="legacy",
        has_spread=False,
    ),
    Category(
        key="tot_rept",
        label="Total reportable",
        short_label="Total reportable",
        prefix=r"tot_rept_positions",
        report="legacy",
    ),
)


def categories_for(report: str) -> tuple[Category, ...]:
    return LEGACY_CATEGORIES if report == "legacy" else DISAGGREGATED_CATEGORIES


def default_categories(report: str) -> list[str]:
    if report == "legacy":
        return ["noncomm", "comm"]
    return ["m_money", "prod_merc", "swap"]


# --------------------------------------------------------------------------
# Analytics defaults
# --------------------------------------------------------------------------
CHANGE_PERIODS: dict[str, int] = {"1w": 1, "4w": 4, "13w": 13, "26w": 26, "52w": 52}
DEFAULT_LOOKBACK_WEEKS = 156  # 3y window for z-scores and the COT index
MIN_LOOKBACK_OBS = 26

HISTORY_WINDOWS: dict[str, int | None] = {
    "1 year": 1,
    "2 years": 2,
    "3 years": 3,
    "5 years": 5,
    "10 years": 10,
    "All history": None,
}
DEFAULT_HISTORY_WINDOW = "3 years"

UNITS: dict[str, str] = {
    "Contracts": "net",
    "% of open interest": "net_pct_oi",
}


@dataclass(frozen=True)
class AppMeta:
    title: str = "Petroleum positioning — CFTC positioning and EIA stocks"
    release_note: str = (
        "CFTC publishes Tuesday positions the following Friday at 15:30 ET."
    )
    source_url: str = "https://publicreporting.cftc.gov/"
    tabs: tuple[str, ...] = field(
        default=("Snapshot", "Compare dates", "Full table", "Breakdown", "Storage", "Data")
    )


META = AppMeta()
