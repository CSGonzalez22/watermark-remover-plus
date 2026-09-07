# watermark-remover-plus

Strip AI provenance markers from content you own - invisible Unicode, homoglyphs,
and C2PA / XMP / EXIF metadata - and get an honest, sourced account of the one
marker class that **cannot** be stripped.

Zero dependencies for the core. One CLI. One Claude Code skill.

```bash
python -m wmrm.cli scan report.docx        # what's in there
python -m wmrm.cli clean logo.png          # -> logo.clean.png
cat draft.md | python -m wmrm.cli clean    # pipes
```

## Why this exists

Since **2026-08-02** - the EU AI Act Article 50 deadline - the major labs mark
generated content. Anthropic watermarks all Claude text with SynthID-Text, with
no opt-out. Google does the same across Gemini. OpenAI signs images and audio
with C2PA and SynthID. Full breakdown with citations: **[RESEARCH.md](RESEARCH.md)**.

Most "watermark remover" tools conflate two very different things. This one
separates them, because the distinction is the whole story:

| Layer | Marker | Can it be removed? |
|---|---|---|
| **A** | Invisible Unicode, homoglyphs, typographic tells | **Yes.** Deterministic and verifiable. |
| **B** | Statistical text watermark (SynthID-Text)	Not by deleting anything. It lives in the token sequence. Only a rewrite touches it, and there is no public detector, so the result cannot be verified. |
| **C** | File metadata: C2PA manifests, XMP, EXIF, doc properties | **Yes.** Deterministic and verifiable. |
Any tool that claims to "remove the SynthID watermark" from text with a character filter is selling you nothing. Layer A and C are real work with a verifiable result; Layer B is a rewrite with an honest asterisk.

## Install

Core is stdlib-only, Python 3.10+. Clone and run:

```bash
git clone https://github.com/CSGonzalez22/watermark-remover-plus
cd watermark-remover-plus
python -m wmrm.cli --help
```

Or install for the `wmrm` command and the optional format handlers:

```bash
pip install .              # core: PNG, JPEG, SVG, OOXML, plain text
pip install '.[pdf]'       # + PDF          (pikepdf)
pip install '.[images]'    # + WebP/TIFF/GIF/BMP/AVIF/HEIC (Pillow)
pip install '.[audio]'     # + MP3/FLAC/M4A/OGG            (mutagen)
pip install '.[all]'
```

Video (MP4/MOV/WebM/MKV) uses `ffmpeg` from `PATH` if present. Missing optional
handlers degrade to a skip notice naming the extra - nothing crashes.

## Usage

### `scan` - report, change nothing

```bash
wmrm scan draft.md
wmrm scan ./exports -r --json
```

Exits `1` when markers are found, `0` when clean. Useful in a pre-commit hook or
CI step.

### `clean` - strip layers A and C

```bash
wmrm clean photo.jpg               # writes photo.clean.jpg
wmrm clean ./docs -r --in-place    # keeps a .bak next to each file
cat draft.md | wmrm clean > out.md # findings go to stderr, text to stdout
```

Flags: `--nfkc` (full Unicode normalization), `--keep-typography` (leave smart
quotes and em dashes alone), `--keep-homoglyphs`, `--force` (with `--in-place`,
skip the backup), `--json`.

Cleaning is **idempotent** - running it twice changes nothing the second time.
Non-Latin text is safe: homoglyph substitution only fires inside tokens that
already contain Latin letters, so Cyrillic or Greek prose passes through
untouched. Accents are preserved (`Café` stays `Café`).

### `brief` - the Layer B rewrite plan

```bash
wmrm brief article.md > brief.txt
```

Emits the source split into ~150-word blocks plus the rewrite rules that
actually destroy a token-sequence watermark: no verbatim sentences, changed
sentence boundaries, reordered clauses, swapped connectives, facts and quotes
preserved. Feed it to any model, or let the bundled skill drive it.

There is deliberately **no bundled ML model**. If you are running this from an
agent, the agent is already a better paraphraser than anything that would fit in
this repo.

### `diff` - did the rewrite actually change anything

```bash
wmrm diff original.md rewritten.md
# shared 4-grams: 12.4% (target: under 30%)
```

Exits `1` if too much of the original token sequence survived. This measures
lexical overlap, **not** watermark presence - no public detector exists to check
that against.

## What each format loses

| Format | Removed |
|---|---|
| PNG | `caBX` (C2PA), `iTXt`/`tEXt`/`zTXt` (XMP, comments), `eXIf`, `iCCP` |
| JPEG | `APP1`-`APP15` (EXIF, XMP, C2PA JUMBF), `COM` |
| SVG | `<metadata>`, RDF blocks, `c2pa:`/`dc:`/`xmp:` attributes, comments |
| docx / xlsx / pptx / odt / epub | `docProps/*`, `meta.xml`, C2PA parts, archive timestamps |
| PDF | `/Info`, XMP `/Metadata`, embedded name tree |
| WebP / TIFF / GIF / BMP / AVIF / HEIC | everything - re-encoded from pixels only |
| MP3 / FLAC / M4A / OGG | all tags |
| MP4 / MOV / WebM | container metadata (`-map_metadata -1`, stream copy) |
| txt / md / html / json / csv | layer A only |

Structural and colour-critical chunks are preserved, so images still render
correctly. Nothing is overwritten unless you pass `--in-place`.

**Not removed:** Google's SynthID pixel and audio watermarks, which are embedded
in the signal and survive crop, filters, and compression. Stripping metadata
does not touch them, and this tool does not pretend otherwise.

## Claude Code skill

```bash
cp -r skills/watermark-remover-plus ~/.claude/skills/
```

Then just ask: *"clean the provenance markers out of report.docx"*. The skill
runs `scan`, runs `clean`, and - for text where the statistical watermark
matters - drives the Layer B rewrite block by block and checks the result with
`wmrm diff`.

## Automatic cleaning (Claude Code hook)

To clean every file an agent writes, without asking:

```bash
cp hooks/wmrm_autoclean.py ~/.claude/hooks/
```

Then register it in `~/.claude/settings.json`, alongside any hooks you already
have - append a new entry, don't replace the array:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python \"~/.claude/hooks/wmrm_autoclean.py\"",
            "timeout": 25
          }
        ]
      }
    ]
  }
}
```

Two scopes, deliberately different:

| Files | Cleaned |
|---|---|
| `.md` `.txt` `.rst` `.html` | Everything - invisibles, smart punctuation, homoglyphs |
| `.py` `.js` `.ts` `.go` `.yml` ... | Invisibles only |
| Anything else | Untouched |

Source files get the narrow treatment on purpose: normalizing quotes or dashes
inside code rewrites string literals, which is a behavior change, not a cleanup.
The hook never blocks - it exits 0 even when `wmrm` is missing or errors - and
stays silent unless it actually changed something.

What a hook **cannot** do: touch what the model types into the chat, or remove a
statistical watermark. Hooks fire on tool calls, and Layer B needs a rewrite.

## Tests

```bash
python -m unittest discover -s tests -t .
```

Ten tests, stdlib `unittest`, no framework, no fixtures. Covers idempotency,
non-Latin safety, PNG chunk surgery, JPEG segment walking with the scan data
intact, SVG metadata removal, and OOXML part dropping.

## Scope and limits


Built for content you own: stripping copy-paste Unicode junk, removing metadata before publishing (a C2PA manifest carries edit history and timestamps you may not want public), and reducing false positives from AI-detector tooling on work you actually wrote or heavily edited.

Not built for, and not appropriate for, passing off AI-generated work as human where disclosure is required - academic submissions, legal filings, journalism, regulated advertising. Layer B is best-effort and unverifiable; treating its output as proof of anything is a mistake.

Prior art and inspiration: guillaumemeyer/watermarks-remover, which covers more formats behind an HTTP service. This one trades that for a single stdlib CLI and a research file that shows its work.

## License

MIT
