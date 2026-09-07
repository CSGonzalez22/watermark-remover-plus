---
name: watermark-remover-plus
description: Strip AI provenance markers from text and files the user owns - invisible Unicode, homoglyphs, and C2PA/XMP/EXIF metadata - and drive the paraphrase rewrite that is the only thing that touches a statistical (SynthID-Text) watermark. Use when the user asks to remove watermarks, strip metadata, clean invisible characters, remove AI fingerprints, scrub C2PA / Content Credentials, or make their own text stop tripping AI detectors.
---

# watermark-remover-plus

Three marker classes, three different answers. Do not conflate them; the user's
expectations depend on knowing which one they have.

| Layer | Marker | Handling |
|---|---|---|
| A | Invisible Unicode, homoglyphs, smart punctuation | `wmrm clean` — deterministic |
| C | C2PA / XMP / EXIF / doc properties | `wmrm clean` — deterministic |
| B | Statistical text watermark (SynthID-Text) | Rewrite, driven by you — best effort, unverifiable |

Background and citations: `RESEARCH.md` in the repo.

## Workflow

### 1. Scan first, always

```bash
python -m wmrm.cli scan <path>          # or: wmrm scan <path>
python -m wmrm.cli scan <dir> -r --json
```

Report what was found before changing anything. Exit code 1 means markers
present.

### 2. Clean layers A and C

```bash
python -m wmrm.cli clean <path>              # writes <name>.clean.<ext>
python -m wmrm.cli clean <path> --in-place   # keeps a .bak
```

Default to the non-destructive form unless the user asked for in-place. Report
what came out. This step is verifiable — re-run `scan` to confirm zero findings.

Stop here if the content is a file with no meaningful prose, or if the user only
cared about metadata.

### 3. Layer B, only when it applies and only after saying so

Say this once, plainly, before starting:

> The statistical watermark lives in the word choices themselves, so it can only
> be removed by rewriting the text. No public detector exists, so I cannot verify
> the result — this is best effort.

Skip Layer B entirely when the text is short (under ~300 words), primarily code,
or primarily factual/structured. Those carry little watermark signal to begin
with, and rewriting them costs meaning for nothing. Say that rather than doing
busywork.

Otherwise:

```bash
python -m wmrm.cli brief <path> > brief.txt
```

Then rewrite **block by block**, following the brief:

1. Preserve meaning, facts, numbers, names, and quotations exactly.
2. No sentence survives verbatim. Change sentence boundaries — split long ones,
   merge short ones.
3. Reorder clauses. Flip voice where it still reads naturally.
4. Swap connectives and discourse markers.
5. Leave code blocks, direct quotations, and citations untouched and say so.
6. Keep the register the user's text already had. Do not make it blander.

### 4. Check the rewrite

```bash
python -m wmrm.cli diff <original> <rewritten>
```

Under 30% shared 4-grams. Above that, the token sequence largely survived — go
back and rewrite the blocks that barely moved. Be explicit that this measures
lexical overlap, not watermark presence.

## Scope

This is for content the user owns. Ordinary uses: cleaning copy-paste junk,
stripping metadata before publishing (C2PA manifests carry edit history and
timestamps), reducing false positives on work they wrote or heavily edited.

If the user's stated purpose is submitting AI-generated work as their own where
disclosure is required — academic submission, legal filing, journalism —
say once that the tool does not make that safe or accurate, then do what they
asked with the caveats intact. Never claim the watermark is "gone."

## Notes

- Cleaning is idempotent; running twice is harmless.
- Non-Latin text is safe — homoglyph substitution only fires inside tokens that
  already contain Latin letters.
- Missing optional handlers (PDF, WebP, audio) report which extra to install
  rather than failing.
- Google's SynthID pixel/audio watermark is embedded in the signal, not the
  metadata. Nothing here removes it. Say so if the user asks about images.
