import struct
import unittest
import zipfile
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory

from wmrm import files, rewrite, text


def png_chunk(ctype: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data))


def make_png(extra: list[tuple[bytes, bytes]]) -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    out = files.PNG_SIG + png_chunk(b"IHDR", ihdr)
    for ctype, data in extra:
        out += png_chunk(ctype, data)
    return out + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")


class TextLayer(unittest.TestCase):
    def test_strips_invisibles_and_normalizes(self):
        dirty = "He​llo­ — wоrld…\U000e0041"
        out, findings = text.clean(dirty)
        self.assertEqual(out, "Hello - world...")
        kinds = {f.kind for f in findings}
        self.assertTrue({"zero-width", "soft", "unicode", "typography", "homoglyph"} <= kinds)

    def test_idempotent(self):
        once, _ = text.clean("a​—b c")
        twice, findings = text.clean(once)
        self.assertEqual(once, twice)
        self.assertEqual(findings, [])

    def test_keeps_real_non_latin(self):
        # Pure Cyrillic must survive: it is not a homoglyph attack.
        out, _ = text.clean("привет")
        self.assertEqual(out, "привет")

    def test_keeps_accents(self):
        out, _ = text.clean("Café naïve")
        self.assertEqual(out, "Café naïve")


class PngLayer(unittest.TestCase):
    def test_drops_c2pa_and_text_chunks(self):
        raw = make_png([(b"caBX", b"jumbf-manifest"), (b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00x")])
        clean, findings = files.strip_png(raw)
        self.assertNotIn(b"caBX", clean)
        self.assertNotIn(b"jumbf-manifest", clean)
        self.assertNotIn(b"iTXt", clean)
        self.assertEqual(len(findings), 2)
        self.assertIn(b"IHDR", clean)
        self.assertIn(b"IDAT", clean)
        self.assertTrue(clean.endswith(png_chunk(b"IEND", b"")))

    def test_clean_png_unchanged(self):
        raw = make_png([])
        clean, findings = files.strip_png(raw)
        self.assertEqual(raw, clean)
        self.assertEqual(findings, [])


class JpegLayer(unittest.TestCase):
    def test_drops_app1_keeps_scan(self):
        payload = b"Exif\x00\x00SECRET-PROVENANCE"
        app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
        dqt = b"\xff\xdb" + struct.pack(">H", 4) + b"\x00\x00"
        scan = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00DATA\xff\xd9"
        raw = b"\xff\xd8" + app1 + dqt + scan
        clean, findings = files.strip_jpeg(raw)
        self.assertNotIn(b"SECRET-PROVENANCE", clean)
        self.assertIn(b"DATA", clean)
        self.assertIn(dqt, clean)
        self.assertEqual(len(findings), 1)


class SvgLayer(unittest.TestCase):
    def test_drops_metadata_block(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" c2pa:manifest="abc">'
            "<metadata><rdf:RDF>claim</rdf:RDF></metadata>"
            '<rect width="1" height="1"/></svg>'
        )
        out, findings = files.strip_svg(svg)
        self.assertNotIn("claim", out)
        self.assertNotIn("c2pa:manifest", out)
        self.assertIn("<rect", out)
        self.assertEqual(len(findings), 2)


class ZipLayer(unittest.TestCase):
    def test_drops_docprops(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "a.docx"
            dst = Path(d) / "b.docx"
            with zipfile.ZipFile(src, "w") as z:
                z.writestr("word/document.xml", "<w:document/>")
                z.writestr("docProps/core.xml", "<creator>Claude</creator>")
                z.writestr("docProps/app.xml", "<app/>")
            findings = files.strip_zip(src, dst)
            with zipfile.ZipFile(dst) as z:
                names = z.namelist()
            self.assertEqual(names, ["word/document.xml"])
            self.assertEqual(sum(1 for f in findings if f.kind == "ooxml-part"), 2)


class Dispatch(unittest.TestCase):
    def test_source_file_is_cleaned_by_sniff(self):
        # .py is in no extension list; content sniffing must still catch it.
        with TemporaryDirectory() as d:
            src = Path(d) / "mod.py"
            dst = Path(d) / "out.py"
            src.write_text('x = "a​b"\n', encoding="utf-8")
            findings = files.clean_file(src, dst, text_opts={"typography": False})
            self.assertEqual(dst.read_text(encoding="utf-8"), 'x = "ab"\n')
            self.assertTrue(findings)

    def test_binary_is_skipped_not_mangled(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "blob.dat"
            dst = Path(d) / "out.dat"
            src.write_bytes(b"\x00\x01\x02binary")
            findings = files.clean_file(src, dst)
            self.assertFalse(dst.exists())
            self.assertEqual(findings[0].kind, "skipped")

    def test_in_place_survives_a_skipped_file(self):
        # Regression: cmd_clean used to crash renaming a tmp that no handler wrote.
        from wmrm import cli

        with TemporaryDirectory() as d:
            src = Path(d) / "blob.dat"
            src.write_bytes(b"\x00\xffkeep me")
            rc = cli.main(["clean", str(src), "--in-place", "--force"])
            self.assertEqual(rc, 0)
            self.assertEqual(src.read_bytes(), b"\x00\xffkeep me")


class RewriteLayer(unittest.TestCase):
    def test_blocks_and_overlap(self):
        para = "word " * 100
        blocks = rewrite.split_blocks((para + "\n\n") * 4, target_words=150)
        self.assertEqual(len(blocks), 4)
        self.assertEqual(rewrite.overlap("the cat sat on the mat", "the cat sat on the mat"), 1.0)
        self.assertLess(rewrite.overlap("the cat sat on the mat", "a feline rested upon a rug"), 0.1)


if __name__ == "__main__":
    unittest.main()
