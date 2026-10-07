"""Collation marks and page numbers: small annotations that help verify
an imposed sheet is correct once printed and folded, without needing to
read the actual story content.

Collation mark convention used here: one filled bar per signature, drawn
once -- on the outermost sheet's outward-facing side (the one visible on
a stack of gathered, folded-but-unstapled signatures without unfolding
any of them) -- at a height that depends only on the signature's index --
so, gathered in order, the marks step down the spine in a staircase; a
missing, duplicated, or swapped signature breaks the pattern. This is a
reasonable, clearly-documented default, not a specific bindery's house
convention -- check it against a physical test signature (`--test-sheet`)
before a real print run.

Page numbers are a plainer, finer-grained check: a small label in every
panel showing which trim page landed there, so you can verify the whole
sheet reads in the right order after folding without needing to read the
actual content.
"""
from __future__ import annotations

import pikepdf

MARK_WIDTH_PT = 18.0
MARK_HEIGHT_PT = 6.0
MARGIN_PT = 36.0  # top/bottom keepout

PAGE_NUMBER_FONT_SIZE_PT = 6.0
PAGE_NUMBER_MARGIN_PT = 4.0
_HELVETICA_DIGIT_WIDTH_EM = 0.556  # AFM advance width, uniform across 0-9 -- lets
# a plain numeric label be centered without a full font-metrics dependency.


def _fill_rect(x: float, y: float, w: float, h: float) -> bytes:
    return f"q 0 0 0 rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f Q\n".encode()


def add_collation_mark(
    page: pikepdf.Object,
    sheet_height_pt: float,
    spine_x_pt: float,
    signature_index: int,
    signature_count: int,
) -> None:
    """Draw one collation-mark bar on `page`, centered at `spine_x_pt`.
    Callers should only call this once per signature (the outermost
    sheet's outward face), not once per sheet -- see module docstring."""
    n = max(signature_count, 1)
    usable = max(sheet_height_pt - 2 * MARGIN_PT, 0.0)
    step = usable / n
    y_top = sheet_height_pt - MARGIN_PT - (signature_index - 1) * step - MARK_HEIGHT_PT
    x = spine_x_pt - MARK_WIDTH_PT / 2
    page.contents_add(_fill_rect(x, y_top, MARK_WIDTH_PT, MARK_HEIGHT_PT))


def add_page_number(
    page: pikepdf.Object, page_num: int, cell_x: float, cell_y: float, cell_w: float, cell_h: float,
) -> None:
    """A small, unobtrusive page-number label centered along the bottom
    edge of one panel's cell (cell_x/cell_y/cell_w/cell_h, in points) --
    just the trim page number, to help verify every panel landed where
    it should once printed and folded."""
    text = str(page_num)
    font = pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica
    )
    font_name = str(page.add_resource(font, pikepdf.Name.Font))
    text_width = len(text) * _HELVETICA_DIGIT_WIDTH_EM * PAGE_NUMBER_FONT_SIZE_PT
    x = cell_x + (cell_w - text_width) / 2
    y = cell_y + PAGE_NUMBER_MARGIN_PT
    stream = (
        f"q BT {font_name} {PAGE_NUMBER_FONT_SIZE_PT:g} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm "
        f"({text}) Tj ET Q\n"
    ).encode()
    page.contents_add(stream)
