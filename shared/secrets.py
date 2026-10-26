"""Secrets, read the same way by every module.

``secret()`` looks in the environment first, then in Streamlit's secrets (the
``.streamlit/secrets.toml`` file locally, the Secrets box on Community Cloud).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import streamlit as st


def secret(name: str) -> str | None:
    """Environment first, then Streamlit secrets (which raise if there is no file)."""
    value = os.getenv(name)
    if value:
        return value
    try:
        found = st.secrets.get(name)
    except Exception:  # noqa: BLE001 - no secrets file is a normal state
        return None
    return str(found) if found else None


def problem(name: str = "ANTHROPIC_API_KEY") -> str:
    """Why a secret was not found, in words; "" if it was found.

    Streamlit says exactly what is wrong, but secret() hides that on purpose (no
    secrets file is a normal state). This turns it into something readable. It
    never repeats a value: Streamlit's own parse errors can quote one.
    """
    if os.getenv(name):
        return ""
    local = Path.cwd() / ".streamlit" / "secrets.toml"
    try:
        found = st.secrets.get(name)
    except Exception as error:  # noqa: BLE001 - we are explaining it, not hiding it
        parsed = re.search(r"Error parsing secrets file at (.+?): .*?line (\d+)", str(error))
        if parsed:
            return (
                f"The secrets file {parsed.group(1)} could not be read (the problem is "
                f"near line {parsed.group(2)}). Each value needs straight double quotes, "
                f'like {name} = "your-value".'
            )
        return (
            "No secrets file was found. Streamlit looks for "
            f"{local} (the folder you started streamlit from) and "
            f"{Path.home() / '.streamlit' / 'secrets.toml'}."
        )
    if found:
        return ""
    try:
        names = [str(key) for key in st.secrets.keys()]
    except Exception:  # noqa: BLE001
        names = []
    if name in names:
        return f"The {name} line in the secrets file is empty."
    if names:
        return (
            f"The secrets file was read but has no {name}. The names it does contain "
            f"are: {', '.join(names)}. The line must sit at the top, above any [section] "
            "heading, spelled exactly as shown."
        )
    return f"The secrets file was read but has no {name} line."
