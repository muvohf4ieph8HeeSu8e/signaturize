"""Shared test helpers: a dependency-free numbered-page PDF writer and
poppler-based text extraction, so PDF-level tests need no TeX or PDF
library; plus a minimal synthetic epub for CLI end-to-end tests."""
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest


def write_numbered_pdf(path: Path, n_pages: int, width_pt: float = 396, height_pt: float = 612) -> Path:
    """Write an n-page PDF whose page i shows the large number i, centred.

    Hand-rolled PDF (base-14 Helvetica, no compression) so it needs no
    library. Each page's number is the only text on it, so extracted text
    identifies which source page ended up where after imposition.
    """
    objects: list[bytes] = []  # objects[i] is PDF object number i+1

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")   # placeholder, filled once the page tree id is known
    pages = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    kids = []
    for i in range(1, n_pages + 1):
        text = str(i)
        content = (
            f"BT /F1 72 Tf {width_pt / 2 - 20 * len(text):.1f} {height_pt / 2:.1f} Td ({text}) Tj ET"
        ).encode()
        c = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        p = add(
            f"<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 {width_pt} {height_pt}] "
            f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {c} 0 R >>".encode()
        )
        kids.append(p)
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages} 0 R >>".encode()
    objects[pages - 1] = (
        "<< /Type /Pages /Kids [" + " ".join(f"{k} 0 R" for k in kids) + f"] /Count {n_pages} >>"
    ).encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path


def pdf_text(pdf: Path, page: int, crop: tuple[int, int, int, int] | None = None) -> str:
    """Text of one 1-indexed page via pdftotext, optionally cropped to
    (x, y, width, height) in points from the page's top-left."""
    cmd = ["pdftotext", "-f", str(page), "-l", str(page), "-layout"]
    if crop is not None:
        x, y, w, h = crop
        cmd += ["-x", str(x), "-y", str(y), "-W", str(w), "-H", str(h)]
    return subprocess.run(cmd + [str(pdf), "-"], capture_output=True, text=True, check=True).stdout.strip()


def pdf_page_size_in(pdf: Path, page: int = 1) -> tuple[float, float]:
    """(width_in, height_in) of one 1-indexed page via pdfinfo -- the
    *effective*, as-rendered/as-printed size, honoring a /Rotate of 90 or
    270 by swapping width/height (pdfinfo's own "size:" line always
    reports the raw, unrotated MediaBox, so this reads its separate
    "rot:" line too). With -f/-l narrowing to one page, poppler labels
    the lines "Page N size:"/"Page N rot:" rather than "Page size:"/"Page
    rot:" (its unnarrowed, single-page-doc phrasing) -- match on
    "size:"/"pts" and "rot:" rather than a fixed prefix to handle both."""
    out = subprocess.run(
        ["pdfinfo", "-f", str(page), "-l", str(page), str(pdf)],
        capture_output=True, text=True, check=True,
    ).stdout
    size_line = next(l for l in out.splitlines() if "size:" in l and "pts" in l)
    w_pt, h_pt = (float(x) for x in size_line.split(":", 1)[1].split("pts")[0].split("x"))
    rot_line = next(l for l in out.splitlines() if "rot:" in l)
    rotation = int(rot_line.split(":", 1)[1].strip())
    if rotation in (90, 270):
        w_pt, h_pt = h_pt, w_pt
    return w_pt / 72.0, h_pt / 72.0


requires_poppler = pytest.mark.skipif(
    shutil.which("pdftotext") is None or shutil.which("pdfinfo") is None,
    reason="poppler-utils not installed",
)
requires_latex = pytest.mark.skipif(
    shutil.which("pdflatex") is None or shutil.which("pandoc") is None,
    reason="pdflatex/pandoc not installed",
)


_CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_CONTENT_OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>A Tiny Test Tale</dc:title>
    <dc:creator>Jane Doe</dc:creator>
    <dc:identifier id="id">http://www.gutenberg.org/12345</dc:identifier>
  </metadata>
  <manifest>
    <item id="pg-header" href="body.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="pg-header"/>
  </spine>
</package>
"""

_BODY_XHTML = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>
<h2 id="pgepubid1">A Tiny Test Tale</h2>
<p>Once upon a time, in a very small book, there lived a very short story.</p>
<p>It had just enough words to fill a single signature, and not one more.</p>
</body>
</html>
"""


def write_minimal_epub(path: Path) -> Path:
    """A minimal but valid epub (one untitled tale, no images) satisfying
    ingest/epub.py's extract() -- used by the CLI end-to-end tests
    (test_cli_ingest.py, test_cli_typeset.py, test_cli_build.py)."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _CONTENT_OPF)
        zf.writestr("OEBPS/body.xhtml", _BODY_XHTML)
    return path
