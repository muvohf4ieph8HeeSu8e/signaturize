"""Collation marks: a stagger of marks along each signature's spine fold,
so a bindery (or you) can tell at a glance whether signatures are present,
in order, and right-side-up once a book is gathered.

Convention used here: one filled bar per signature, on the back face at
the spine (the fold line all of a signature's nested sheets share),
printed identically on every sheet of that signature, at a height that
depends only on the signature's index -- so, folded and gathered in
order, the marks step down the spine in a staircase; a missing,
duplicated, or swapped signature breaks the pattern. This is a
reasonable, clearly-documented default, not a specific bindery's house
convention -- check it against a physical test signature (`--test-sheet`)
before a real print run.
"""
from __future__ import annotations

import pikepdf

MARK_WIDTH_PT = 18.0
MARK_HEIGHT_PT = 6.0
MARGIN_PT = 36.0  # top/bottom keepout


def _fill_rect(x: float, y: float, w: float, h: float) -> bytes:
    return f"q 0 0 0 rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f Q\n".encode()


def add_collation_mark(
    page: pikepdf.Object,
    sheet_height_pt: float,
    spine_x_pt: float,
    signature_index: int,
    signature_count: int,
) -> None:
    """Draw one collation-mark bar on `page`, centered at `spine_x_pt`."""
    n = max(signature_count, 1)
    usable = max(sheet_height_pt - 2 * MARGIN_PT, 0.0)
    step = usable / n
    y_top = sheet_height_pt - MARGIN_PT - (signature_index - 1) * step - MARK_HEIGHT_PT
    x = spine_x_pt - MARK_WIDTH_PT / 2
    page.contents_add(_fill_rect(x, y_top, MARK_WIDTH_PT, MARK_HEIGHT_PT))


def add_slug_line(page: pikepdf.Object, text: str) -> None:
    """A small identifying text line near the bottom-left corner -- book
    name, signature/sheet index, face -- to catch mixed-up loose sheets."""
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    font = pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica
    )
    font_name = str(page.add_resource(font, pikepdf.Name.Font))
    stream = f"q BT {font_name} 6 Tf 1 0 0 1 6 6 Tm ({escaped}) Tj ET Q\n".encode()
    page.contents_add(stream)
