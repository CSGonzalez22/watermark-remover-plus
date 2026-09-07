"""Layer C: strip provenance metadata (C2PA / XMP / EXIF / doc properties).

Core formats are handled with the standard library. Everything else degrades
to an optional dependency and says which extra to install.
"""
from __future__ import annotations

import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

from .report import Finding

# --- PNG --------------------------------------------------------------------

# Structural + colour-critical chunks. Everything else (caBX = C2PA, iTXt/tEXt/
# zTXt = XMP & comments, eXIf, iCCP) is provenance surface and gets dropped.
PNG_KEEP = {
    b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS",
    b"gAMA", b"cHRM", b"sRGB", b"bKGD", b"sBIT",
    b"acTL", b"fcTL", b"fdAT",  # APNG
}
PNG_SIG = b"\x89PNG\r\n\x1a\n"

CHUNK_LABELS = {
    b"caBX": "C2PA manifest (caBX chunk)",
    b"iTXt": "XMP / text chunk",
    b"tEXt": "text chunk",
    b"zTXt": "compressed text chunk",
    b"eXIf": "EXIF block",
    b"iCCP": "ICC profile",
}


def strip_png(data: bytes) -> tuple[bytes, list[Finding]]:
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG")
    out = bytearray(PNG_SIG)
    findings: list[Finding] = []
    i = len(PNG_SIG)
    while i + 8 <= len(data):
        (length,) = struct.unpack(">I", data[i : i + 4])
        ctype = data[i + 4 : i + 8]
        end = i + 12 + length
        if ctype in PNG_KEEP:
            out += data[i:end]
        else:
            label = CHUNK_LABELS.get(ctype, ctype.decode("latin1"))
            findings.append(Finding("file", "png-chunk", f"dropped PNG {label}"))
        i = end
        if ctype == b"IEND":
            break
    return bytes(out), findings


# --- JPEG -------------------------------------------------------------------

JPEG_LABELS = {0xE1: "EXIF/XMP", 0xE2: "ICC or C2PA (JUMBF)", 0xED: "Photoshop/IPTC"}


def strip_jpeg(data: bytes) -> tuple[bytes, list[Finding]]:
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("not a JPEG")
    out = bytearray(b"\xff\xd8")
    findings: list[Finding] = []
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker == 0xDA:  # start of scan: rest is entropy-coded, copy verbatim
            out += data[i:]
            break
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        seg_end = i + 2 + length
        # ponytail: APP0 is kept so viewers keep density info; APP1..APP15 and
        # COM are pure metadata surface.
        if (0xE1 <= marker <= 0xEF) or marker == 0xFE:
            label = JPEG_LABELS.get(marker, "APP%d" % (marker - 0xE0))
            findings.append(Finding("file", "jpeg-segment", f"dropped JPEG {label} segment"))
        else:
            out += data[i:seg_end]
        i = seg_end
    return bytes(out), findings


# --- SVG / XML --------------------------------------------------------------

# ponytail: regex, not ElementTree - ET rewrites namespace prefixes and reflows
# the whole document, which mangles hand-authored SVG.
SVG_BLOCKS = re.compile(
    r"<(metadata|rdf:RDF|c2pa:[\w.-]+|dc:[\w.-]+)\b[^>]*?(?:/>|>.*?</\1>)",
    re.DOTALL | re.IGNORECASE,
)
SVG_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
SVG_ATTRS = re.compile(
    r"\s+(?:c2pa|dc|xmp|xmpMM|exif):[\w.-]+\s*=\s*(?:\"[^\"]*\"|'[^']*')", re.IGNORECASE
)


def strip_svg(text: str) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    text, n = SVG_BLOCKS.subn("", text)
    if n:
        findings.append(Finding("file", "svg-metadata", "dropped <metadata>/RDF/C2PA elements", n))
    text, n = SVG_ATTRS.subn("", text)
    if n:
        findings.append(Finding("file", "svg-attr", "dropped provenance attributes", n))
    text, n = SVG_COMMENT.subn("", text)
    if n:
        findings.append(Finding("file", "svg-comment", "dropped XML comments", n))
    return text, findings


# --- ZIP containers (docx/xlsx/pptx/odt/epub) --------------------------------

ZIP_DROP = re.compile(r"(^docProps/|^meta\.xml$|c2pa|^customXml/|thumbnail\.)", re.IGNORECASE)
ZIP_EXT = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".epub"}
EPOCH = (1980, 1, 1, 0, 0, 0)


def strip_zip(src: Path, dst: Path) -> list[Finding]:
    findings: list[Finding] = []
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if ZIP_DROP.search(item.filename):
                findings.append(Finding("file", "ooxml-part", f"dropped part {item.filename}"))
                continue
            info = zipfile.ZipInfo(item.filename, date_time=EPOCH)
            info.compress_type = item.compress_type
            info.external_attr = item.external_attr
            zout.writestr(info, zin.read(item.filename))
    findings.append(Finding("file", "zip-mtime", "zeroed archive timestamps"))
    return findings


# --- optional-dependency formats --------------------------------------------

def strip_pdf(src: Path, dst: Path) -> list[Finding]:
    try:
        import pikepdf
    except ImportError:
        return [Finding("file", "skipped", "PDF needs pikepdf: pip install watermark-remover-plus[pdf]")]
    with pikepdf.open(src) as pdf:
        pdf.docinfo.clear()
        for key in ("/Metadata", "/Names", "/PieceInfo"):
            if key in pdf.Root:
                del pdf.Root[key]
        pdf.save(dst, linearize=False)
    return [Finding("file", "pdf-metadata", "cleared /Info, XMP, embedded name tree")]


def strip_with_pillow(src: Path, dst: Path) -> list[Finding]:
    try:
        from PIL import Image
    except ImportError:
        return [Finding("file", "skipped", f"{src.suffix} needs Pillow: pip install watermark-remover-plus[images]")]
    with Image.open(src) as im:
        im.load()
        clean = Image.new(im.mode, im.size)
        clean.putdata(list(im.getdata()))
        clean.save(dst)
    return [Finding("file", "reencoded", "re-encoded pixels only, all metadata dropped")]


def strip_audio(src: Path, dst: Path) -> list[Finding]:
    try:
        import mutagen
    except ImportError:
        return [Finding("file", "skipped", f"{src.suffix} needs mutagen: pip install watermark-remover-plus[audio]")]
    shutil.copyfile(src, dst)
    f = mutagen.File(dst)
    if f is None:
        return [Finding("file", "skipped", f"mutagen cannot parse {src.name}")]
    f.delete()
    f.save()
    return [Finding("file", "audio-tags", "deleted all audio tags")]


def strip_video(src: Path, dst: Path) -> list[Finding]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return [Finding("file", "skipped", "video needs ffmpeg on PATH")]
    proc = subprocess.run(
        [ffmpeg, "-y", "-i", str(src), "-map_metadata", "-1", "-c", "copy", str(dst)],
        capture_output=True,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace")[-200:]
        return [Finding("file", "error", f"ffmpeg failed: {tail}")]
    return [Finding("file", "container-metadata", "stripped container metadata (pixel watermark survives)")]


# --- dispatch ---------------------------------------------------------------

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".html", ".htm"}
PILLOW_EXT = {".webp", ".tiff", ".tif", ".gif", ".bmp", ".avif", ".heic", ".heif"}
AUDIO_EXT = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
NATIVE_EXT = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}


def supported(path: Path) -> bool:
    e = path.suffix.lower()
    return (
        e in NATIVE_EXT or e in ZIP_EXT or e in TEXT_EXT
        or e in PILLOW_EXT or e in AUDIO_EXT or e in VIDEO_EXT
    )


def clean_file(src: Path, dst: Path, *, text_opts: dict | None = None) -> list[Finding]:
    """Write the cleaned version of `src` to `dst`. Returns findings."""
    from . import text as textlayer

    ext = src.suffix.lower()
    if ext == ".png":
        data, f = strip_png(src.read_bytes())
        dst.write_bytes(data)
        return f
    if ext in {".jpg", ".jpeg"}:
        data, f = strip_jpeg(src.read_bytes())
        dst.write_bytes(data)
        return f
    if ext == ".svg":
        out, f = strip_svg(src.read_text(encoding="utf-8", errors="replace"))
        out, f2 = textlayer.clean(out, **(text_opts or {}))
        dst.write_text(out, encoding="utf-8")
        return f + f2
    if ext in ZIP_EXT:
        return strip_zip(src, dst)
    if ext == ".pdf":
        return strip_pdf(src, dst)
    if ext in PILLOW_EXT:
        return strip_with_pillow(src, dst)
    if ext in AUDIO_EXT:
        return strip_audio(src, dst)
    if ext in VIDEO_EXT:
        return strip_video(src, dst)
    if ext in TEXT_EXT or not ext:
        raw = src.read_text(encoding="utf-8", errors="replace")
        out, f = textlayer.clean(raw, **(text_opts or {}))
        dst.write_text(out, encoding="utf-8", newline="")
        return f
    return [Finding("file", "skipped", f"no handler for {ext}")]


def scan_file(src: Path) -> list[Finding]:
    """Non-destructive: report what a clean would remove."""
    from . import text as textlayer

    ext = src.suffix.lower()
    try:
        if ext == ".png":
            return strip_png(src.read_bytes())[1]
        if ext in {".jpg", ".jpeg"}:
            return strip_jpeg(src.read_bytes())[1]
        if ext == ".svg":
            out, f = strip_svg(src.read_text(encoding="utf-8", errors="replace"))
            return f + textlayer.scan(out)
        if ext in ZIP_EXT:
            with zipfile.ZipFile(src) as z:
                return [
                    Finding("file", "ooxml-part", f"metadata part {n}")
                    for n in z.namelist()
                    if ZIP_DROP.search(n)
                ]
        if ext in TEXT_EXT or not ext:
            return textlayer.scan(src.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, OSError, zipfile.BadZipFile) as e:
        return [Finding("file", "error", str(e))]
    return [Finding("file", "unknown", f"{ext}: binary metadata not scanned, run clean to strip")]
