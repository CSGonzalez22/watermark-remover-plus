"""Layer A: deterministic scrubbing of invisible / lookalike characters.

This layer does NOT touch statistical watermarks (SynthID-Text). It removes
characters that carry payloads or fingerprint copy-paste provenance, and
normalizes typographic lookalikes back to ASCII.
"""
from __future__ import annotations

import re
import unicodedata

from .report import Finding

# --- character classes ------------------------------------------------------

# Removed outright. Value is the human label used in findings.
INVISIBLE: dict[str, str] = {}


def _fill(label: str, *ranges: tuple[int, int]) -> None:
    for lo, hi in ranges:
        for cp in range(lo, hi + 1):
            INVISIBLE[chr(cp)] = label


_fill("zero-width / bidi control", (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064), (0x2066, 0x2069))
_fill("byte-order mark", (0xFEFF, 0xFEFF))
_fill("soft hyphen", (0x00AD, 0x00AD))
_fill("unicode tag (hidden ASCII payload)", (0xE0000, 0xE007F))
_fill("variation selector", (0xFE00, 0xFE0F), (0xE0100, 0xE01EF))
_fill("word joiner / invisible operator", (0x2061, 0x2064))
_fill("interlinear annotation", (0xFFF9, 0xFFFB))

# Collapsed to a plain space.
EXOTIC_SPACE = {
    " ": "no-break space",
    " ": "ogham space",
    "᠎": "mongolian vowel separator",
    " ": "narrow no-break space",
    " ": "medium mathematical space",
    "　": "ideographic space",
}
for _cp in range(0x2000, 0x200B):
    EXOTIC_SPACE[chr(_cp)] = "exotic space"

# Typography tells -> ASCII.
TYPOGRAPHY = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "…": "...", "′": "'", "″": '"',
    "«": '"', "»": '"',
    "⁄": "/", "−": "-",
}

# Non-Latin glyphs that render like Latin ones. Only substituted inside tokens
# that are otherwise Latin, so real Cyrillic/Greek text is left alone.
CONFUSABLES = {
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M",
    "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
    "Х": "X", "а": "a", "е": "e", "о": "o", "р": "p",
    "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H",
    "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O",
    "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "ο": "o",
    "Ѕ": "S", "һ": "h", "‐": "-",
}

_LATIN = re.compile(r"[A-Za-z]")
_TOKEN = re.compile(r"\w+", re.UNICODE)


def _demix(text: str) -> tuple[str, int]:
    """Replace confusables inside tokens that already contain Latin letters."""
    hits = 0

    def fix(m: re.Match[str]) -> str:
        nonlocal hits
        tok = m.group(0)
        if not _LATIN.search(tok):
            return tok
        out = []
        for ch in tok:
            repl = CONFUSABLES.get(ch)
            if repl is not None:
                hits += 1
                out.append(repl)
            else:
                out.append(ch)
        return "".join(out)

    return _TOKEN.sub(fix, text), hits


def scan(text: str) -> list[Finding]:
    """Report markers without modifying anything."""
    _, findings = clean(text)
    return findings


def clean(
    text: str,
    *,
    typography: bool = True,
    confusables: bool = True,
    nfkc: bool = False,
) -> tuple[str, list[Finding]]:
    """Return (cleaned_text, findings). Idempotent."""
    findings: list[Finding] = []
    counts: dict[str, int] = {}
    out = []

    for ch in text:
        label = INVISIBLE.get(ch)
        if label is not None:
            counts[label] = counts.get(label, 0) + 1
            continue
        space = EXOTIC_SPACE.get(ch)
        if space is not None:
            counts[space] = counts.get(space, 0) + 1
            out.append(" ")
            continue
        out.append(ch)
    text = "".join(out)

    for label, n in counts.items():
        kind = label.split()[0].strip("/")
        findings.append(Finding("text", kind, f"stripped {label}", n))

    if typography:
        n = 0
        for src, dst in TYPOGRAPHY.items():
            c = text.count(src)
            if c:
                n += c
                text = text.replace(src, dst)
        if n:
            findings.append(Finding("text", "typography", "normalized smart punctuation to ASCII", n))

    if confusables:
        text, n = _demix(text)
        if n:
            findings.append(Finding("text", "homoglyph", "replaced non-Latin lookalike letters", n))

    if nfkc:
        norm = unicodedata.normalize("NFKC", text)
        if norm != text:
            findings.append(Finding("text", "nfkc", "applied NFKC normalization", 1))
            text = norm

    return text, findings
