"""Turn the bot's commentary text into a title plus a grid of section cards.

The commentary is Markdown written by a model, so the layout is read from it
loosely: a heading line (``#``/``##``/``###``), or a line that opens with an
emoji (``🔑 Key Positioning Shifts — ...``), starts a new section. The first
heading with no emoji, ahead of the sections, is the title.

The HTML is built here rather than by Streamlit's Markdown renderer for two
reasons: the cards need equal heights (a CSS grid does that), and Streamlit
treats a pair of ``$`` signs as LaTeX, which garbles prices like "$114 to $135".
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$")
_RULE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
_END = re.compile(r"^\W*end\W*$", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")


@dataclass(frozen=True)
class Section:
    title: str
    body: str


def _starts_with_emoji(text: str) -> bool:
    return bool(text) and unicodedata.category(text[0]) in {"So", "Sk"}


def _clean_title(text: str) -> str:
    return re.sub(r"\*+", "", text).strip(" :—-")


def parse(text: str) -> tuple[str, str, list[Section]]:
    """Return (title, intro, sections). Sections is empty when no structure is found.

    ``intro`` is any text that comes before the first section and is not the title.
    """
    title = ""
    sections: list[tuple[str, list[str]]] = []
    preface: list[str] = []

    def open_section(heading: str, rest: str = "") -> None:
        sections.append((_clean_title(heading), [rest] if rest else []))

    for raw in text.splitlines():
        line = raw.rstrip()
        if _RULE.match(line) or _END.match(line.replace("—", "").strip()):
            continue
        match = _HEADING.match(line)
        if match:
            heading = match.group(1)
            if _starts_with_emoji(_clean_title(heading)) or sections:
                open_section(heading)
            elif not title:
                title = _clean_title(heading)
            else:
                open_section(heading)
            continue
        bare = re.sub(r"^[*\s]+", "", line)
        if _starts_with_emoji(bare):
            # "🔑 **Key Positioning Shifts** — text" or "**🔑 Key Positioning Shifts**"
            split = re.match(r"^(.+?)(?:\*\*)?\s+[—–-]\s+(.*)$", bare)
            if split and len(_clean_title(split.group(1))) <= 60:
                open_section(split.group(1), split.group(2))
            elif len(_clean_title(bare)) <= 60:
                open_section(bare)
            else:
                (sections[-1][1] if sections else preface).append(line)
            continue
        (sections[-1][1] if sections else preface).append(line)

    intro = "\n".join(preface).strip()
    if not sections:
        return title, intro, []
    return title, intro, [Section(head, "\n".join(body).strip()) for head, body in sections if head]


def _inline(text: str) -> str:
    out = html.escape(text, quote=False).replace("$", "&#36;")
    out = _LINK.sub(r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    return _ITALIC.sub(r"<em>\1</em>", out)


def body_html(text: str) -> str:
    """Paragraphs, bullet lists, **bold** and *italic*: all this text needs."""
    parts: list[str] = []
    paragraph: list[str] = []
    bullets: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            parts.append("<p>" + "<br>".join(_inline(p) for p in paragraph) + "</p>")
            paragraph.clear()

    def flush_bullets() -> None:
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{_inline(b)}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for line in text.splitlines():
        if not line.strip():
            flush_paragraph()
            flush_bullets()
            continue
        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            flush_bullets()
            parts.append(f"<p><strong>{_inline(_clean_title(heading.group(1)))}</strong></p>")
            continue
        bullet = _BULLET.match(line)
        if bullet:
            flush_paragraph()
            bullets.append(bullet.group(1))
        else:
            flush_bullets()
            paragraph.append(line.strip())
    flush_paragraph()
    flush_bullets()
    return "".join(parts)


def note_html(text: str) -> str:
    """The commentary as one line of HTML, or "" when it has no sections to lay out."""
    title, intro, sections = parse(text)
    if not sections:
        return ""
    cards = "".join(
        f'<div class="cot-card"><div class="cot-card-title">{_inline(s.title)}</div>'
        f"{body_html(s.body)}</div>"
        for s in sections
    )
    head = f'<div class="cot-note-title">{_inline(title)}</div>' if title else ""
    lead = body_html(intro) if intro else ""
    return f'<div class="cot-note">{head}{lead}<div class="cot-grid">{cards}</div></div>'
