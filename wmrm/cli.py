"""wmrm - watermark-remover-plus CLI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import files as filelayer
from . import rewrite as rewritelayer
from . import text as textlayer
from .report import Report

EPILOG = """\
three layers:
  A  invisible unicode + homoglyphs   deterministic, verifiable
  C  file metadata (C2PA/XMP/EXIF)    deterministic, verifiable
  B  statistical watermark (SynthID)  `wmrm brief` only - needs a rewrite,
                                      best effort, cannot be verified

intended for content you own. not for passing off AI work as human where
disclosure is required (academia, legal filings, journalism).
"""


def _stdio_text() -> str:
    return sys.stdin.buffer.read().decode("utf-8", errors="replace")


def _iter_paths(root: Path, recursive: bool):
    if root.is_file():
        yield root
        return
    it = root.rglob("*") if recursive else root.glob("*")
    for p in sorted(it):
        if p.is_file() and filelayer.supported(p):
            yield p


def _out_path(src: Path, in_place: bool) -> Path:
    if in_place:
        return src
    return src.with_name(f"{src.stem}.clean{src.suffix}")


def cmd_scan(args) -> int:
    report = Report()
    if args.path == "-":
        report.extend(textlayer.scan(_stdio_text()), "<stdin>")
    else:
        for p in _iter_paths(Path(args.path), args.recursive):
            report.extend(filelayer.scan_file(p), str(p))
    print(report.to_json() if args.json else report.to_text())
    return 1 if report else 0


def cmd_clean(args) -> int:
    opts = {"nfkc": args.nfkc, "typography": not args.keep_typography,
            "confusables": not args.keep_homoglyphs}
    report = Report()

    if args.path == "-":
        out, findings = textlayer.clean(_stdio_text(), **opts)
        sys.stdout.buffer.write(out.encode("utf-8"))
        report.extend(findings, "<stdin>")
        print(report.to_json() if args.json else report.to_text(), file=sys.stderr)
        return 0

    for src in _iter_paths(Path(args.path), args.recursive):
        dst = _out_path(src, args.in_place)
        if args.in_place and not args.force:
            backup = src.with_suffix(src.suffix + ".bak")
            if backup.exists():
                print(f"refusing: {backup} already exists (use --force)", file=sys.stderr)
                return 2
            backup.write_bytes(src.read_bytes())
        if args.in_place:
            tmp = src.with_suffix(src.suffix + ".tmp")
            findings = filelayer.clean_file(src, tmp, text_opts=opts)
            # A handler that skipped the file never wrote tmp. Leave the
            # original alone rather than crashing on the rename.
            if tmp.exists():
                tmp.replace(dst)
        else:
            findings = filelayer.clean_file(src, dst, text_opts=opts)
        report.extend(findings, str(dst))

    print(report.to_json() if args.json else report.to_text(), file=sys.stderr)
    return 0


def cmd_brief(args) -> int:
    raw = _stdio_text() if args.path == "-" else Path(args.path).read_text(
        encoding="utf-8", errors="replace"
    )
    sys.stdout.buffer.write(rewritelayer.make_brief(raw, args.words).encode("utf-8"))
    return 0


def cmd_diff(args) -> int:
    before = Path(args.before).read_text(encoding="utf-8", errors="replace")
    after = Path(args.after).read_text(encoding="utf-8", errors="replace")
    frac = rewritelayer.overlap(before, after)
    print(f"shared 4-grams: {frac:.1%} (target: under 30%)")
    return 0 if frac < 0.30 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wmrm",
        description="Remove AI provenance markers from content you own.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="report markers, change nothing (exit 1 if any found)")
    s.add_argument("path", nargs="?", default="-", help="file, directory, or - for stdin")
    s.add_argument("-r", "--recursive", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("clean", help="strip layer A + C markers")
    c.add_argument("path", nargs="?", default="-", help="file, directory, or - for stdin")
    c.add_argument("-r", "--recursive", action="store_true")
    c.add_argument("--json", action="store_true")
    c.add_argument("--in-place", action="store_true", help="overwrite, keeping a .bak")
    c.add_argument("--force", action="store_true", help="with --in-place, skip the .bak")
    c.add_argument("--nfkc", action="store_true", help="also apply NFKC normalization")
    c.add_argument("--keep-typography", action="store_true", help="keep smart quotes and dashes")
    c.add_argument("--keep-homoglyphs", action="store_true", help="keep non-Latin lookalikes")
    c.set_defaults(func=cmd_clean)

    b = sub.add_parser("brief", help="emit a layer B rewrite brief for an agent")
    b.add_argument("path", nargs="?", default="-")
    b.add_argument("--words", type=int, default=150, help="target words per block")
    b.set_defaults(func=cmd_brief)

    d = sub.add_parser("diff", help="check how much of the original survived a rewrite")
    d.add_argument("before")
    d.add_argument("after")
    d.set_defaults(func=cmd_diff)

    return p


def main(argv: list[str] | None = None) -> int:
    # ponytail: Windows consoles default to cp1252 and blow up on a non-ASCII
    # path in a finding. Reports are ours to encode; force utf-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
