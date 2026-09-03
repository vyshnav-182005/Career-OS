"""
Provider job descriptions arrive as HTML fragments (Jooble snippets, Adzuna
descriptions) full of tags, encoded entities, and layout artifacts. Anything
that reads that text - the LLM prompts in the ATS/optimization flows, and the
job detail view in the UI - wants plain readable prose instead.

This module is the single backend definition of "clean job text". The frontend
mirrors it in `frontend/src/lib/utils/jobText.ts`; keep the two in sync.
"""

import html
import re
import unicodedata
from typing import Optional

# Tags whose content is markup/behaviour rather than prose - dropped whole.
_DROP_BLOCK_RE = re.compile(
    r"<(script|style|head|noscript)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
# Tags that end a visual line.
_LINE_BREAK_RE = re.compile(r"<\s*(br|hr)\s*/?\s*>", re.IGNORECASE)
# Tags that end a visual block.
_BLOCK_END_RE = re.compile(
    r"<\s*/?\s*(p|div|section|article|table|tr|h[1-6]|ul|ol|blockquote)\b[^>]*>",
    re.IGNORECASE,
)
# List items become bullet lines so structure survives tag stripping.
_LIST_ITEM_RE = re.compile(r"<\s*li\b[^>]*>", re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
# HTML comments and stray CDATA/doctype noise.
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Bullet glyphs providers sprinkle through text; normalized to a single marker.
_BULLET_CHARS = "•‣▪●◦⁃∙·‧❑➢➜⮚"
_BULLET_LINE_RE = re.compile(rf"^\s*(?:[{_BULLET_CHARS}]|[-*+o])\s+", re.MULTILINE)

# Zero-width / bidi / soft-hyphen characters that survive entity decoding and
# render as invisible garbage or break word matching.
_INVISIBLE_RE = re.compile(r"[​-‏‪-‮⁠﻿­]")
# Non-breaking and other exotic spaces -> plain space.
_ODD_SPACE_RE = re.compile(r"[   -   　]")

_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r" +([,.;:!?%)])")
_ORPHAN_PUNCT_LINE_RE = re.compile(r"^[\s\-*_=~.,;:|]+$")

# Provider boilerplate that adds nothing for a reader or an LLM.
_BOILERPLATE_RE = re.compile(
    r"^\s*(read more|show more|apply now|view job|see full description)\s*[.:]?\s*$",
    re.IGNORECASE,
)


def _strip_markup(text: str) -> str:
    text = _COMMENT_RE.sub(" ", text)
    text = _DROP_BLOCK_RE.sub(" ", text)
    text = _LINE_BREAK_RE.sub("\n", text)
    text = _LIST_ITEM_RE.sub("\n• ", text)
    text = _BLOCK_END_RE.sub("\n", text)
    return _ANY_TAG_RE.sub(" ", text)


def _decode_entities(text: str) -> str:
    """
    Decodes named/numeric entities, twice: providers routinely double-encode
    (`&amp;nbsp;`), which a single pass leaves as a literal `&nbsp;`.
    """
    decoded = html.unescape(text)
    if "&" in decoded:
        decoded = html.unescape(decoded)
    return decoded


def clean_html_text(raw: Optional[str]) -> str:
    """
    Turns a raw provider HTML fragment into plain, readable multi-line text:
    tags stripped (block structure preserved as line breaks), entities decoded,
    invisible/control characters removed, bullets normalized to "• ", and
    whitespace collapsed. Returns "" for empty input.
    """
    if not raw:
        return ""

    text = _strip_markup(str(raw))
    text = _decode_entities(text)
    # A second strip: decoding can reveal tags that were entity-encoded
    # (`&lt;p&gt;`), a very common double-encoding artifact.
    if "<" in text and ">" in text:
        text = _strip_markup(text)

    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_RE.sub("", text)
    text = _ODD_SPACE_RE.sub(" ", text)
    # Drop remaining control characters (keep \n and \t).
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or not unicodedata.category(ch).startswith("C"))
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")

    text = _BULLET_LINE_RE.sub("• ", text)

    lines = []
    for line in text.split("\n"):
        line = _MULTI_SPACE_RE.sub(" ", line).strip()
        if not line:
            lines.append("")
            continue
        if _ORPHAN_PUNCT_LINE_RE.match(line) or _BOILERPLATE_RE.match(line):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def clean_job_description(raw: Optional[str]) -> str:
    """Alias kept explicit at call sites that clean a job description."""
    return clean_html_text(raw)


def summarize_text(raw: Optional[str], max_chars: int = 180) -> str:
    """
    Single-line preview of a description for card/list UIs, truncated on a word
    boundary. Cleans first, so callers never preview raw markup.
    """
    text = " ".join(clean_html_text(raw).split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0].rstrip(",;:.-• ")
    return f"{cut}…"
