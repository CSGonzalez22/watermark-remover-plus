# What the labs actually mark, and how

Research digest behind this tool. Everything here is sourced from vendor
documentation or peer-reviewed / preprint work — links inline. Last updated
2026-09-06.

## The short version

| Vendor | Text | Images / audio / video |
|---|---|---|
| **Anthropic (Claude)** | SynthID-Text statistical watermark. Model-level, every surface (claude.ai, API, Bedrock, Vertex). No opt-out. Models released on or after **2026-08-02**. | Signed **C2PA** manifests on `.png`, `.jpg`, `.svg` |
| **Google (Gemini, Imagen, Veo, Lyria, NotebookLM)** | SynthID-Text — they invented it | SynthID pixel / audio / video watermark, plus C2PA |
| **OpenAI (ChatGPT, DALL·E, Sora)** | Not shipped. Stated intent only. | **C2PA** Content Credentials since 2026-05-19; **SynthID** on images, and on audio since 2026-07-31. Public checker: `openai.com/verify` |

The forcing function is the **EU AI Act, Article 50**, whose machine-readable
marking obligation for generative providers took effect **2026-08-02** — the
same date Anthropic's watermark went live.

## How the text watermark actually works

This is the part most write-ups get wrong, and it determines what a removal
tool can and cannot do.

It is **not** invisible Unicode. It is not a hidden character, a zero-width
space, or a payload smuggled in variation selectors. You cannot find it with a
hex editor and you cannot delete it.

An LLM produces text by sampling one token at a time from a probability
distribution. SynthID-Text ([Dathathri, See et al., *Nature* 634, 818–823,
Oct 2024](https://www.nature.com/articles/s41586-024-08025-4)) changes only the
*source of randomness* used for that sampling. A pseudorandom function keyed by
a secret and seeded by the preceding token window assigns g-values to candidate
tokens; sampling is then tournament-biased toward high-g-value candidates.
Among tokens the model considered roughly equally good, the watermarked model
systematically prefers one specific subset.

Anthropic's own framing: *"the words that Claude picks are still random, but
one can check the sequence of words and see if it's consistent with the choices
Claude would make."* ([How Claude's text watermarking works, 2026-08-14](https://www.anthropic.com/news/claude-text-watermark))

Consequences:

- The mark lives in **which words were chosen, in what order**. Nothing else.
- Detection is a statistical test over the whole passage. It returns a
  likelihood, never a yes/no.
- The key reveals nothing about the user, org, or conversation — it is one
  global key, not a per-user fingerprint.
- Copy-paste preserves it perfectly. Plain-text export preserves it. Changing
  fonts, file formats, or line wrapping preserves it.

## What breaks it

From the vendors' own limitation notes and from independent evaluation:

1. **Short text.** Below a few hundred tokens there is not enough signal.
   Anthropic and Google both say so explicitly.
2. **Low-entropy text.** Factual answers, definitions, code, structured output.
   If there was only one reasonable next token, there was no choice to bias.
3. **Paraphrasing.** The strongest attack, and by a wide margin. Regenerating
   the passage with a *different* model re-samples every token, so the biased
   sequence is gone. [An empirical forensic-readiness evaluation
   (arXiv:2607.16010)](https://arxiv.org/html/2607.16010v1) reports **98.3% of
   initially-detected texts lost the watermark after paraphrase**; for KGW and
   Unigram schemes the conditional removal rate was 100%. See also
   [Adversarial Paraphrasing (arXiv:2506.07001)](https://arxiv.org/pdf/2506.07001)
   and [ETH SRI Lab's probing of SynthID-Text](https://www.sri.inf.ethz.ch/blog/probingsynthid).
4. **Translation / back-translation.** A special case of the above.
5. **Heavy human editing.** Light editing survives; a real rewrite does not.
   Anthropic states the watermark "can't distinguish between Claude wrote this
   and Claude edited this," and that edited content degrades detectability.

What does *not* break it: deleting characters, changing whitespace, swapping
quote styles, re-encoding the file, changing case. None of those touch the token
sequence in a way the detector cares about.

## The other marker class: invisible characters

Separate problem, often conflated with the above. Real, and deterministic to
fix:

- Zero-width and bidi controls (`U+200B`–`U+200F`, `U+202A`–`U+202E`)
- Unicode Tags block (`U+E0000`–`U+E007F`) — can encode arbitrary ASCII
  invisibly inside a string
- Variation selectors, soft hyphens, BOM, exotic spaces
- Homoglyphs: Cyrillic `о` for Latin `o`, and friends

These come from copy-paste pipelines, rich-text editors, prompt-injection
payloads, and occasionally from deliberate tagging. They are not the
SynthID-style watermark, but they *are* a fingerprint and they *are* removable.

## File-side provenance: C2PA

[C2PA](https://c2pa.org/) manifests are signed metadata: what tool made the
asset, when, and what edits were applied. Where they live:

| Format | Carrier |
|---|---|
| PNG | `caBX` ancillary chunk |
| JPEG | `APP11` JUMBF segment (and `APP1` for XMP/EXIF) |
| SVG / XML | `<metadata>` element, RDF, `c2pa:` attributes |
| PDF | `/Metadata` XMP stream, `/Info` dictionary |
| MP4 / MOV | `uuid` box in the container |
| OOXML (docx/xlsx/pptx) | `docProps/*` parts |

C2PA is *metadata*, not steganography. Stripping it is deterministic and
complete. Note that a C2PA manifest also leaks edit history, timestamps, and
sometimes device or account hints — reason enough to strip it before publishing
even if you have no interest in AI provenance.

Google's SynthID pixel/audio watermark is a different animal: it is embedded in
the signal itself, survives crop/compression/filters, and stripping container
metadata does **not** remove it. This tool does not claim to.

## Detection availability, as of 2026-09-06

- **Anthropic**: detection API in private preview for eligible organizations.
  No public endpoint.
- **Google**: SynthID Detector portal, waitlisted, journalists and media
  professionals. Gemini will also answer "was this made by Google AI?" for
  uploaded content.
- **OpenAI**: `openai.com/verify` is public, images and audio only.

There is therefore **no public way to verify** that a text watermark has been
removed. Any tool claiming verified text-watermark removal is guessing. This
one says so out loud.

## Sources

- [How Claude's text watermarking works — Anthropic, 2026-08-14](https://www.anthropic.com/news/claude-text-watermark)
- [How Claude marks AI-generated content — Claude Help Center](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content)
- [Anthropic shares more details about how Claude's new watermarks will work — TechCrunch, 2026-08-15](https://techcrunch.com/2026/08/15/anthropic-shares-more-details-about-how-claudes-new-watermarks-will-work/)
- [SynthID — Google DeepMind](https://deepmind.google/models/synthid/)
- [Scalable watermarking for identifying large language model outputs — *Nature*, Oct 2024](https://www.nature.com/articles/s41586-024-08025-4)
- [Advancing content provenance — OpenAI, 2026-05-19](https://openai.com/index/advancing-content-provenance/)
- [Provenance signals (Content Credentials, SynthID) — OpenAI Help Center](https://help.openai.com/en/articles/8912793-provenance-signals-content-credentials-synthid-in-openai-generated-content)
- [AI Watermark Evidence Fails Forensic Readiness (arXiv:2607.16010)](https://arxiv.org/html/2607.16010v1)
- [Adversarial Paraphrasing (arXiv:2506.07001)](https://arxiv.org/pdf/2506.07001)
- [Probing Google DeepMind's SynthID-Text — ETH SRI Lab](https://www.sri.inf.ethz.ch/blog/probingsynthid)
- [C2PA specification](https://c2pa.org/)
- [EU AI Act, Article 50](https://artificialintelligenceact.eu/article/50/)
