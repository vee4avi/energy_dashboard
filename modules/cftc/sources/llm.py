"""Anthropic API calls for the on-demand analysis. No Streamlit.

Two calls, mirroring the Telegram bot: an optional dated news search, then the
commentary. ``anthropic`` is imported lazily so the rest of the app (and the
tests) work without it installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.cftc.config import settings

SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}


class AnalysisError(RuntimeError):
    """Anything that stops an analysis; the message is safe to show the user."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    searches: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.searches + other.searches,
        )

    def cost(self, model: str) -> float | None:
        prices = settings.MODEL_PRICES.get(model)
        if prices is None:
            return None
        per_in, per_out = prices
        return (
            self.input_tokens * per_in / 1e6
            + self.output_tokens * per_out / 1e6
            + self.searches * settings.WEB_SEARCH_PRICE_PER_1000 / 1000
        )


def client(api_key: str):
    try:
        import anthropic
    except ImportError as error:  # pragma: no cover - depends on the install
        raise AnalysisError("The 'anthropic' package is not installed.") from error
    return anthropic.Anthropic(api_key=api_key)


def _usage(response) -> Usage:
    usage = getattr(response, "usage", None)
    server = getattr(usage, "server_tool_use", None)
    return Usage(
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        searches=int(getattr(server, "web_search_requests", 0) or 0),
    )


def _text(response) -> str:
    return " ".join(
        block.text for block in response.content if getattr(block, "text", None)
    ).strip()


def fetch_news(api, model: str, prompt: str) -> tuple[str, Usage]:
    """News summary via web search. A failed search returns '' rather than raising,
    so the analysis can still run on positioning alone."""
    try:
        response = api.messages.create(
            model=model,
            max_tokens=4000,
            tools=[SEARCH_TOOL],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:  # noqa: BLE001 - news is optional
        return "", Usage()
    return _text(response), _usage(response)


def write_commentary(api, model: str, prompt: str) -> tuple[str, Usage]:
    try:
        response = api.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as error:  # noqa: BLE001
        raise AnalysisError(f"The analysis request failed ({type(error).__name__}).") from error
    text = _text(response)
    if not text:
        raise AnalysisError("The model returned no text.")
    return text, _usage(response)
