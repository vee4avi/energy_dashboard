"""Tests for saved commentary, the prompt builder, the model client and the Snapshot panel.

Nothing here makes a paid call: the Anthropic client is replaced by a fake.

Run with:  python tests/test_analysis.py
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["COT_DEMO"] = "1"  # services reads this at import time

import pandas as pd  # noqa: E402

from modules.cftc.analytics import cot, narrative  # noqa: E402
from modules.cftc.config import settings  # noqa: E402
from modules.cftc.sources import commentary, demo, llm  # noqa: E402

# What the Telegram bot writes (see build_record in cot_report_bot.py).
SAMPLE = {
    "schema": 1,
    "report": "disaggregated",
    "basis": "combined",
    "report_date": "2026-09-29",
    "prior_date": "2026-09-22",
    "generated_at": "2026-10-02T20:35:00+00:00",
    "model": "claude-sonnet-4-6",
    "commentary": "🔑 Key Positioning Shifts — Managed money bought crude.",
    "news": "OPEC+ held output.",
    "contracts": {"Brent LD (NYMEX)": {}, "WTI Fin (NYMEX)": {}},
}


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class _Block:
    def __init__(self, text: str) -> None:
        self.text = text


class _Response:
    def __init__(self, text: str, tokens_in: int, tokens_out: int, searches: int = 0) -> None:
        self.content = [_Block(text)]
        self.usage = types.SimpleNamespace(
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            server_tool_use=types.SimpleNamespace(web_search_requests=searches),
        )


class FakeAPI:
    """Stands in for anthropic.Anthropic: records calls, never touches the network."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("tools"):
            return _Response("OPEC+ held output; crude rallied.", 12_000, 600, searches=4)
        return _Response("🔑 Key Positioning Shifts — fake analysis.", 3_000, 700)


def _summary() -> tuple[pd.DataFrame, dict[str, str]]:
    enriched = cot.enrich(demo.positions("disaggregated"))
    dates = cot.report_dates(enriched)
    summary = cot.summarise(
        cot.as_of_slice(enriched, dates[0]), cot.as_of_slice(enriched, dates[1])
    )
    return summary, {c.key: c.ui_label for c in settings.categories_for("disaggregated")}


# --------------------------------------------------------------------------
# Saved commentary
# --------------------------------------------------------------------------
def test_load_and_match() -> None:
    raw = {
        "2026-09-29.json": json.dumps(SAMPLE),
        "broken.json": "{not json",
        "empty.json": json.dumps({**SAMPLE, "commentary": "  "}),
        "foreign.json": json.dumps({"hello": 1}),
    }
    parsed = [commentary._parse_text(text) for text in raw.values()]
    records = {r.report_date: r for r in parsed if r is not None}

    assert list(records) == [pd.Timestamp("2026-09-29")], "only the valid record loads"
    record = records[pd.Timestamp("2026-09-29")]
    assert record.products == ("Brent LD (NYMEX)", "WTI Fin (NYMEX)")
    assert record.basis == "combined" and record.model == "claude-sonnet-4-6"

    this_week, last_week = pd.Timestamp("2026-09-29"), pd.Timestamp("2026-09-22")
    assert commentary.match(records, this_week, last_week) is record
    assert commentary.match(records, this_week, pd.Timestamp("2026-09-01")) is None, "4 weeks is a different comparison"
    assert commentary.match(records, this_week, None) is None
    assert commentary.match(records, pd.Timestamp("2026-09-22"), last_week) is None
    assert commentary.match(records, this_week, last_week, report="legacy") is None
    assert commentary.for_date(records, this_week) is record
    assert commentary.for_date(records, pd.Timestamp("2020-01-07")) is None
    print("commentary files: ok")


# --------------------------------------------------------------------------
# Prompt building
# --------------------------------------------------------------------------
def test_prompt_building() -> None:
    summary, labels = _summary()
    data, omitted = narrative.data_block(summary, labels, 1000)
    assert omitted == 0
    assert "ΔNet=" in data and "COT index" in data and "OI:" in data

    small, left_out = narrative.data_block(summary, labels, 10)
    assert left_out > 0 and small, "row cap trims the smallest books and says how many"

    prompt = narrative.build_prompt(
        data, "29 Sep 2026", "22 Sep 2026", 1, "Futures only", "disaggregated", news="NEWS-TEXT"
    )
    assert "NEWS-TEXT" in prompt and "week-on-week" in prompt and "29 Sep 2026" in prompt
    longer = narrative.build_prompt(
        data, "29 Sep 2026", "30 Jun 2026", 13, "Futures only", "disaggregated"
    )
    assert "over the 13 weeks" in longer and "Do not flag caveats" in longer
    assert "(3 smaller" in narrative.build_prompt(data, "a", "b", 1, "c", "d", omitted=3)
    assert "between 2026-09-22 and 2026-09-29" in narrative.news_prompt("2026-09-22", "2026-09-29")
    print("prompt building: ok")


# --------------------------------------------------------------------------
# Model client and cost
# --------------------------------------------------------------------------
def test_usage_cost_and_client_errors() -> None:
    usage = llm.Usage(input_tokens=1_000_000, output_tokens=1_000_000, searches=100)
    assert abs(usage.cost("claude-sonnet-5-5") - (2 + 10 + 1)) < 1e-9
    assert abs(usage.cost("claude-sonnet-4-6") - (3 + 15 + 1)) < 1e-9
    assert usage.cost("some-future-model") is None, "unknown model: no invented price"
    assert (usage + usage).searches == 200

    class Broken:
        messages = None

        def __init__(self) -> None:
            self.messages = self

        def create(self, **_):
            raise RuntimeError("boom")

    text, used = llm.fetch_news(Broken(), "m", "p")
    assert text == "" and used == llm.Usage(), "a failed search must not stop the analysis"
    try:
        llm.write_commentary(Broken(), "m", "p")
    except llm.AnalysisError as error:
        assert "RuntimeError" in str(error) and "boom" not in str(error)
    else:  # pragma: no cover
        raise AssertionError("expected AnalysisError")
    print("usage, cost and error handling: ok")


def test_run_analysis_cost_and_cache() -> None:
    from modules.cftc import services

    services.run_analysis.clear()
    fake = FakeAPI()
    original, llm.client = llm.client, lambda key: fake
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    try:
        args = (
            "Brent (OI: 1)\n  Managed money: L=1 S=1 Net=0 (ΔNet=+1; ΔL=+1, ΔS=+0)",
            0, "29 Sep 2026", "22 Sep 2026", 1, "Futures only", "disaggregated",
            ("2026-09-22", "2026-09-29"), "claude-sonnet-5-5",
        )
        result = services.run_analysis(*args)
        assert len(fake.calls) == 2, "one news search, one commentary"
        assert fake.calls[0]["tools"][0]["name"] == "web_search"
        assert "fake analysis" in result["text"] and result["news_requested"]
        assert result["input_tokens"] == 15_000 and result["output_tokens"] == 1_300
        assert result["searches"] == 4
        assert abs(result["cost"] - (15_000 * 2e-6 + 1_300 * 10e-6 + 4 * 0.01)) < 1e-9

        services.run_analysis(*args)
        assert len(fake.calls) == 2, "an identical request is served from the cache"

        plain = services.run_analysis(*args[:7], None, args[8])
        assert len(fake.calls) == 3 and plain["searches"] == 0 and not plain["news"]
    finally:
        llm.client = original
        os.environ.pop("ANTHROPIC_API_KEY", None)
        services.run_analysis.clear()
    print("run_analysis cost and cache: ok")


# --------------------------------------------------------------------------
# Reading from GitHub (mocked: no network)
# --------------------------------------------------------------------------
class _Reply:
    def __init__(self, code: int, payload=None, text: str = "") -> None:
        self.status_code = code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_github_reader() -> None:
    older = {**SAMPLE, "report_date": "2026-09-22", "prior_date": "2026-09-15"}
    listing = [
        {"type": "file", "name": "2026-09-29.json", "sha": "a1", "download_url": "https://raw/a1"},
        {"type": "file", "name": "2026-09-22.json", "sha": "b2", "download_url": "https://raw/b2"},
        {"type": "file", "name": "README.md", "sha": "c3", "download_url": "https://raw/c3"},
        {"type": "dir", "name": "old", "sha": "d4", "download_url": None},
    ]
    files = {"https://raw/a1": json.dumps(SAMPLE), "https://raw/b2": json.dumps(older)}
    calls: list[tuple] = []
    state = {"listing": _Reply(200, listing)}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, dict(headers or {}), params))
        if "api.github.com" in url:
            return state["listing"]
        return _Reply(200, text=files[url])

    original, commentary.requests.get = commentary.requests.get, fake_get
    commentary._BY_SHA.clear()
    try:
        records = commentary.load_github("me/cot-report-bot", token="secret-token")
        assert sorted(records) == [pd.Timestamp("2026-09-22"), pd.Timestamp("2026-09-29")]
        assert len(calls) == 3, "one listing, two files; README and folders are ignored"
        assert calls[0][1]["Authorization"] == "Bearer secret-token"
        assert calls[0][2] == {"ref": "main"}

        commentary.load_github("me/cot-report-bot", token="secret-token")
        assert len(calls) == 4, "second load re-reads only the listing: files are cached by hash"

        newest_only = commentary.load_github("me/cot-report-bot", max_files=1)
        assert list(newest_only) == [pd.Timestamp("2026-09-29")]

        state["listing"] = _Reply(404, {"message": "Not Found"})
        assert commentary.load_github("me/cot-report-bot") == {}, "no folder yet: not an error"

        for code in (401, 403, 500):
            state["listing"] = _Reply(code, {})
            try:
                commentary.load_github("me/cot-report-bot", token="secret-token")
            except commentary.FetchError as error:
                assert str(code) in str(error) and "secret-token" not in str(error)
            else:  # pragma: no cover
                raise AssertionError(f"expected FetchError for {code}")

        def offline(*_a, **_k):
            raise commentary.requests.ConnectionError("down")

        commentary.requests.get = offline
        try:
            commentary.load_github("me/cot-report-bot")
        except commentary.FetchError as error:
            assert "network" in str(error)
        else:  # pragma: no cover
            raise AssertionError("expected FetchError when offline")

        for bad in ("not a repo", "", "a/b/c", "../x"):
            try:
                commentary.load_github(bad)
            except commentary.FetchError:
                pass
            else:  # pragma: no cover
                raise AssertionError(f"accepted bad repo name {bad!r}")
    finally:
        commentary.requests.get = original
        commentary._BY_SHA.clear()
    print("github reader: ok")


def test_secrets_problem_explains_without_leaking() -> None:
    from modules.cftc import services

    class Fake:
        def __init__(self, get=None, error=None, names=()):
            self._get, self._error, self._names = get, error, list(names)

        def get(self, _name):
            if self._error:
                raise self._error
            return self._get

        def keys(self):
            return self._names

    original = services.st.secrets
    os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        services.st.secrets = Fake(error=Exception("No secrets found. Valid paths are: /x"))
        assert "No secrets file was found" in services.secrets_problem()

        services.st.secrets = Fake(error=Exception(
            "Error parsing secrets file at /home/me/app/.streamlit/secrets.toml: invalid "
            "literal for int() with base 0: 'sk-ant-TOPSECRET' (line 3 column 1 char 40)"))
        said = services.secrets_problem()
        assert "line 3" in said and "/home/me/app/.streamlit/secrets.toml" in said
        assert "TOPSECRET" not in said, "a parse error must never echo the key"

        services.st.secrets = Fake(get=None, names=["general"])
        assert "general" in services.secrets_problem() and "[section]" in services.secrets_problem()

        services.st.secrets = Fake(get=None, names=["ANTHROPIC_KEY"])
        assert "ANTHROPIC_KEY" in services.secrets_problem()

        services.st.secrets = Fake(get="", names=["ANTHROPIC_API_KEY"])
        assert "empty" in services.secrets_problem()

        services.st.secrets = Fake(get=None, names=[])
        assert "no ANTHROPIC_API_KEY line" in services.secrets_problem()

        services.st.secrets = Fake(get="sk-ant-fine")
        assert services.secrets_problem() == ""
        services.st.secrets = Fake(error=Exception("anything"))
        os.environ["ANTHROPIC_API_KEY"] = "from-env"
        assert services.secrets_problem() == "", "an environment variable counts"
    finally:
        services.st.secrets = original
        os.environ.pop("ANTHROPIC_API_KEY", None)
    print("secrets diagnosis: ok")


def test_commentary_source_wording() -> None:
    from modules.cftc import services

    os.environ.pop("COMMENTARY_REPO", None)
    assert "COMMENTARY_REPO is not set" in services.commentary_source()
    os.environ["COMMENTARY_REPO"] = "me/cot-report-bot"
    try:
        assert "me/cot-report-bot" in services.commentary_source()
    finally:
        os.environ.pop("COMMENTARY_REPO", None)
    print("commentary source wording: ok")


def test_load_commentary_reads_github_only() -> None:
    from modules.cftc import services

    week = commentary._parse_text(json.dumps(SAMPLE))
    original_demo, services.DEMO_MODE = services.DEMO_MODE, False
    original_fetch = commentary.load_github
    os.environ.pop("COMMENTARY_REPO", None)
    try:
        services.load_commentary.clear()
        records, note = services.load_commentary()
        assert records == {} and "COMMENTARY_REPO isn't set" in note, "no repo: nothing to show, and it says why"

        os.environ["COMMENTARY_REPO"] = "me/cot-report-bot"
        seen = {}

        def fake(repo, **kw):
            seen.update(repo=repo, **kw)
            return {week.report_date: week}

        commentary.load_github = fake
        services.load_commentary.clear()
        records, note = services.load_commentary()
        assert list(records) == [pd.Timestamp("2026-09-29")] and note == ""
        assert seen["repo"] == "me/cot-report-bot" and seen["folder"] == "commentary"

        def broken(repo, **kw):
            raise commentary.FetchError("network error (ConnectionError)")

        commentary.load_github = broken
        services.load_commentary.clear()
        records, note = services.load_commentary()
        assert records == {} and "Couldn't read commentary from GitHub" in note
        assert "on this computer" not in note, "there is no local fallback any more"
    finally:
        commentary.load_github = original_fetch
        services.DEMO_MODE = original_demo
        os.environ.pop("COMMENTARY_REPO", None)
        services.load_commentary.clear()
    print("commentary loading, github only: ok")


# --------------------------------------------------------------------------
# The Snapshot panel, through Streamlit's AppTest
# --------------------------------------------------------------------------
def _app():
    from streamlit.testing.v1 import AppTest

    from modules.cftc import services

    services.load_commentary.clear()
    services.run_analysis.clear()
    os.chdir(ROOT)
    return AppTest.from_file(str(ROOT / "tests" / "cftc_entry.py"), default_timeout=90)


def _markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def _captions(at) -> str:
    return "\n".join(c.value for c in at.caption)


def test_panel_shows_only_for_the_matching_pair() -> None:
    for name in ("ANTHROPIC_API_KEY", "ANALYSIS_PASSWORD"):
        os.environ.pop(name, None)
    at = _app().run()
    assert not at.exception, [e.value for e in at.exception]
    text = _markdown(at)
    assert "Desk commentary" in text and "DEMO COMMENTARY" in text
    assert "Analyse these dates" not in text, "no API key: the run box stays hidden"
    assert "ANTHROPIC_API_KEY" in _captions(at), "but the page says how to switch it on"
    assert "snap_stack" not in [t.key for t in at.toggle], "tables are always stacked now"
    assert any("futures + options" in i.value.lower() for i in at.info), "basis mismatch is flagged"

    at.selectbox(key="snap_baseline_choice").set_value("4 weeks ago").run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Desk commentary" not in _markdown(at), "a 4-week comparison gets no weekly commentary"
    assert "Saved commentary exists" in _captions(at), "and the page says how to reach it"
    print("commentary panel: ok")


def test_view_only_mode_hides_generation_but_keeps_commentary() -> None:
    from modules.cftc import services

    os.environ["ANTHROPIC_API_KEY"] = "test-key"      # even with a key present
    os.environ["COT_VIEW_ONLY"] = "1"
    os.environ.pop("ANALYSIS_PASSWORD", None)
    try:
        assert services.view_only() and not services.analysis_enabled()
        at = _app().run()
        assert not at.exception, [e.value for e in at.exception]
        text, captions = _markdown(at), _captions(at)
        assert "Desk commentary" in text, "saved commentary is still shown"
        assert "Analyse these dates" not in text
        assert not [b for b in at.button if b.key == "analysis_run"]
        assert "ANTHROPIC_API_KEY" not in captions, "visitors get no setup hints"
        assert "secrets" not in captions.lower()
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("COT_VIEW_ONLY", None)
        services.run_analysis.clear()
    assert not services.view_only()
    print("view-only mode: ok")


def test_on_demand_analysis_flow() -> None:
    from modules.cftc import services
    from modules.cftc.sources import llm as llm_module

    fake = FakeAPI()
    original, llm_module.client = llm_module.client, lambda key: fake
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    os.environ.pop("ANALYSIS_PASSWORD", None)
    try:
        at = _app().run()
        assert not at.exception, [e.value for e in at.exception]
        assert "Analyse these dates" in _markdown(at)

        at.button(key="analysis_run").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert "fake analysis" in _markdown(at)
        assert "≈ $" in _captions(at) and len(fake.calls) == 1

        at.button(key="analysis_run").click().run()
        assert len(fake.calls) == 1, "same dates and filters: no second paid call"

        at.checkbox(key="analysis_news").check().run()
        assert "changed since the last run" in _captions(at)
        at.button(key="analysis_run").click().run()
        assert len(fake.calls) == 3, "news search plus commentary"
        assert "4 web searches" in _captions(at)
    finally:
        llm_module.client = original
        os.environ.pop("ANTHROPIC_API_KEY", None)
        services.run_analysis.clear()
    print("on-demand analysis flow: ok")


def test_access_code_gate() -> None:
    from modules.cftc import services
    from modules.cftc.sources import llm as llm_module

    fake = FakeAPI()
    original, llm_module.client = llm_module.client, lambda key: fake
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    os.environ["ANALYSIS_PASSWORD"] = "open sesame"
    try:
        at = _app().run()
        assert not at.exception, [e.value for e in at.exception]
        assert not [b for b in at.button if b.key == "analysis_run"], "locked until the code is entered"

        at.text_input(key="analysis_code").input("wrong").run()
        assert any("isn't right" in e.value for e in at.error)
        assert not [b for b in at.button if b.key == "analysis_run"]

        at.text_input(key="analysis_code").input("open sesame").run()
        assert not at.exception, [e.value for e in at.exception]
        assert [b for b in at.button if b.key == "analysis_run"], "unlocked"
        assert fake.calls == [], "unlocking costs nothing"
    finally:
        llm_module.client = original
        for name in ("ANTHROPIC_API_KEY", "ANALYSIS_PASSWORD"):
            os.environ.pop(name, None)
        services.run_analysis.clear()
    print("access code gate: ok")


if __name__ == "__main__":
    test_load_and_match()
    test_github_reader()
    test_secrets_problem_explains_without_leaking()
    test_commentary_source_wording()
    test_load_commentary_reads_github_only()
    test_prompt_building()
    test_usage_cost_and_client_errors()
    test_run_analysis_cost_and_cache()
    test_panel_shows_only_for_the_matching_pair()
    test_view_only_mode_hides_generation_but_keeps_commentary()
    test_on_demand_analysis_flow()
    test_access_code_gate()
    print("\nall analysis tests passed")
