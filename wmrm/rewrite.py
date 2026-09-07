"""Layer B: brief generator for statistical (SynthID-Text) watermarks.

There is nothing to strip here. A SynthID-style watermark is a bias in *which*
token was sampled, so it lives in the word sequence itself. The only thing that
reliably destroys it is regenerating that sequence - i.e. paraphrasing with a
different model. This module does not paraphrase; it produces the brief that an
agent (or a person) executes, and blocks the text so long documents stay
tractable.
"""
from __future__ import annotations

import re

BRIEF = """\
# Rewrite brief (Layer B - statistical watermark)

A SynthID-style text watermark is carried by the token sequence, not by any
character you can delete. Deterministic cleaning does not touch it. Rewriting
does, because a different model re-samples every token.

Rules for each block below:
1. Preserve meaning, facts, numbers, names, and quotes exactly.
2. Do not reuse any sentence verbatim. Change sentence boundaries: split long
   sentences, merge short ones.
3. Reorder clauses. Switch voice (active <-> passive) where it still reads well.
4. Swap connectives and discourse markers for different ones.
5. Leave code blocks, literal quotations, and citations untouched - mark them as
   carried over. Rewriting them would change meaning, and short/literal spans
   carry little watermark signal anyway.
6. Target under 30%% shared 4-grams with the source block.

Known ceiling: no public detector exists (Anthropic's is in private preview),
so the result CANNOT be verified. Treat this as best effort, never as a
guarantee. Short, factual, or code-heavy text carries little signal to begin
with - and also loses little by being left alone.

Blocks: %d (about %d words total)
"""


def split_blocks(text: str, target_words: int = 150) -> list[str]:
    """Split on paragraph boundaries, packing to roughly `target_words`."""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    blocks: list[str] = []
    buf: list[str] = []
    count = 0
    for p in paras:
        n = len(p.split())
        if buf and count + n > target_words:
            blocks.append("\n\n".join(buf))
            buf, count = [], 0
        buf.append(p)
        count += n
    if buf:
        blocks.append("\n\n".join(buf))
    return blocks


def make_brief(text: str, target_words: int = 150) -> str:
    blocks = split_blocks(text, target_words)
    parts = [BRIEF % (len(blocks), len(text.split()))]
    for i, b in enumerate(blocks, 1):
        parts.append(f"\n--- BLOCK {i}/{len(blocks)} ({len(b.split())} words) ---\n{b}")
    return "\n".join(parts)


def ngrams(text: str, n: int = 4) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def overlap(before: str, after: str, n: int = 4) -> float:
    """Fraction of the original's n-grams still present. Lower is better."""
    a = ngrams(before, n)
    if not a:
        return 0.0
    return len(a & ngrams(after, n)) / len(a)
