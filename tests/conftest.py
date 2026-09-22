"""Shared test helpers: a dependency-free numbered-page PDF writer and
poppler-based text extraction, so PDF-level tests need no TeX or PDF library."""
import shutil
import subprocess
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


requires_poppler = pytest.mark.skipif(
    shutil.which("pdftotext") is None or shutil.which("pdfinfo") is None,
    reason="poppler-utils not installed",
)
requires_latex = pytest.mark.skipif(
    shutil.which("pdflatex") is None or shutil.which("pandoc") is None,
    reason="pdflatex/pandoc not installed",
)
