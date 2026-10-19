"""Render a SignaturePlan against a source PDF into print-ready sheets,
using pikepdf: each source page becomes a Form XObject placed by an affine
matrix into its panel's cell, with a 180-degree rotation where the fold
simulator (scheme.py) calls for one. One PDF page is written per sheet
face (front, then back if duplex) -- page order is already duplex-ready
print order.

planner.py's sheet_slot 0/1 ("west"/"east" leaves) are placed directly on
their own physical column (slot 0 -> west/left, slot 1 -> east/right) --
no column swap by default. This, together with scheme.py's front/back
Panel assignment, is the original pamphlet pipeline's own proven
imposition convention, carried over exactly (see scheme.py's
sheet_panel_layout() docstring for why a *uniform* column swap was tried
here and reverted: it produced a correctly-placed cover by coincidence
but scrambled every later sheet's order, caught only once a full book,
not just one test sheet, was actually printed and folded).

A standard duplex printer flipping a sheet on its long edge mirrors the
back face's columns left/right relative to the front -- so `duplex_mirror`
(default True) swaps, column for column, which content lands in each
physical cell of the back face only; the cells themselves stay where
they are (the fold line doesn't move), but what's drawn into one cell is
what would otherwise have gone in the other. The front face is never
swapped, mirror or not. This default was wrong (off) until it was
checked, page by page and column by column, against five real,
physically-printed-and-folded books (the original pamphlet pipeline's
own `output/*-booklet.pdf`, via `--landscape-feed`, which matches that
original tool's literal-landscape page convention exactly) -- all five
matched byte-for-byte once `duplex_mirror=True` (see
tests/test_regression_legacy.py). That literal-landscape page is the
default. The optional portrait-page `/Rotate=90` encoding (see below)
computes identical content placement either way and is *claimed* to
print the same once duplexed, but that specific combination
(rotate-flagged page + mirrored back face) hasn't itself been
physically confirmed the way the literal-landscape path has -- verify
it with your own `--test-sheet` first if you choose it. Set
`duplex_mirror=False` only if your printer's duplex unit doesn't mirror
the back face (uncommon).

When `marks` is on (the default), every panel gets a small page-number
label (see marks.add_page_number(); `page_overlay=False` drops just the
label and keeps the collation marks, for a source that already prints its
own page numbers -- see detect.has_printed_page_numbers()) so you can verify order after
printing and folding without reading the actual content, and each
signature's outermost sheet gets one collation mark on its outward face
(see marks.add_collation_mark()) -- not one per sheet, since its purpose
(checking a gathered stack of signatures without unfolding any of them)
only makes sense once per signature.

A scheme like folio needs a logically-landscape sheet for its own panel
math (room for two side-by-side portrait leaves). By default
(`landscape_feed=True`), render() writes a literal landscape PDF page,
which displays upright on screen and is what the physically verified
regression books used. Pass `landscape_feed=False` (CLI:
`--portrait-feed`) to instead build the page content exactly as it
would for a literal landscape page and then set the PDF's standard
`/Rotate = 90` page attribute, so PDF viewers/printers display and print
it rotated into the paper's own natural (portrait) shape -- for printers
that cannot take a landscape page. That encoding is necessarily sideways
in a flat, straight-on preview (on screen, or a print preview); you print
onto portrait paper and physically turn the sheet 90 degrees by hand
before folding. Its rotation direction is a reasoned default, not
something verifiable without a physical print -- verify with a
`--test-sheet` before a full run, the same caution this project already
applies to `duplex_mirror` and to multi-fold schemes.
"""
from __future__ import annotations

from pathlib import Path

import pikepdf

from .marks import add_collation_mark, add_page_number
from .planner import SignaturePlan
from .scheme import Panel, outward_face, sheet_panel_layout

PT_PER_IN = 72.0


def _resolve_cell(cols: int, row: int, col: int, mirror: bool) -> tuple[int, int]:
    """(src_col, slot) for one physical (row, col) position on a sheet
    face -- shared by render()'s own placement loop and sheet_face_pages()
    below, so the two can never drift apart. planner.py's sheet_slot 0/1
    ("west"/"east" leaves) land directly on their own physical column
    (no swap) by default; `mirror` (duplex_mirror), on only for the back
    face of a printer that needs that compensation, swaps it column for
    column -- see this module's docstring."""
    src_col = (cols - 1 - col) if mirror else col
    slot = row * cols + src_col
    return src_col, slot


def sheet_face_pages(
    signature_plan: SignaturePlan, sig_index: int, sheet_index: int, *, duplex_mirror: bool = True,
) -> dict[str, list[int | None]]:
    """The trim-page number landing in each physical column of each face
    of one physical sheet, left-to-right as the sheet lies flat before
    folding -- "front"/"back" (present only for a duplex scheme) are the
    sheet's first/second printed pass; see scheme.py's
    sheet_panel_layout() for which pages end up outward vs inward once
    folded (for folds=1 that's not simply "front" or "back" uniformly --
    see its own docstring). None stands for a blank cell.

    Pure data, computed with the exact same column resolution
    (_resolve_cell) render() itself draws from, so it can't drift from
    what actually gets printed. printguide.py uses this to print a
    verification page-map in PRINTING.md: reading the rendered PDF
    directly to check order is awkward because the back face is
    necessarily drawn in a different column order than it reads once
    folded (see this module's docstring), so a flat before-folding table
    like this one needs no mental page-flipping."""
    scheme = signature_plan.scheme
    rows, cols = scheme.grid
    front_grid, back_grid = sheet_panel_layout(scheme.folds)
    leaves = signature_plan.leaves_of(sig_index, sheet_index)
    by_slot = {leaf.sheet_slot: leaf for leaf in leaves}

    def face_pages(grid: list[list[Panel]], mirror: bool) -> list[int | None]:
        row = 0  # folds in {0, 1}: sheet_panel_layout() only ever returns a single row
        pages: list[int | None] = []
        for col in range(cols):
            src_col, slot = _resolve_cell(cols, row, col, mirror)
            leaf = by_slot.get(slot)
            panel = grid[row][src_col]
            page_num = None if leaf is None else (
                leaf.recto_page if panel.side == "recto" else leaf.verso_page
            )
            pages.append(page_num)
        return pages

    result = {"front": face_pages(front_grid, mirror=False)}
    if scheme.duplex:
        result["back"] = face_pages(back_grid, mirror=duplex_mirror)
    return result


def _placement_matrix(
    src_w: float, src_h: float, cell_x: float, cell_y: float, cell_w: float, cell_h: float, rotation: int
) -> tuple[float, float, float, float, float, float]:
    """Affine matrix (a b c d e f) placing a src_w x src_h page, centered,
    into the cell at (cell_x, cell_y, cell_w, cell_h), optionally rotated
    180 degrees in place."""
    tol = 0.01
    if src_w > cell_w + tol or src_h > cell_h + tol:
        raise ValueError(
            f"source page ({src_w:.2f} x {src_h:.2f}pt) is larger than its sheet "
            f"cell ({cell_w:.2f} x {cell_h:.2f}pt) -- check trim size against the scheme"
        )
    if rotation == 0:
        return 1, 0, 0, 1, cell_x + (cell_w - src_w) / 2, cell_y + (cell_h - src_h) / 2
    if rotation == 180:
        return -1, 0, 0, -1, cell_x + (cell_w + src_w) / 2, cell_y + (cell_h + src_h) / 2
    raise ValueError(f"unsupported rotation {rotation}; only 0 and 180 are defined")


def render(
    source_pdf: Path,
    signature_plan: SignaturePlan,
    outfile: Path,
    *,
    sheets_filter: set[tuple[int, int]] | None = None,
    marks: bool = True,
    page_overlay: bool = True,
    duplex_mirror: bool = True,
    landscape_feed: bool = True,
) -> None:
    """Write imposed sheets to `outfile`. If `sheets_filter` is given, only
    those (signature_index, sheet_index) pairs are rendered (e.g. for a
    one-sheet physical test print). `duplex_mirror` (default True)
    compensates for a standard long-edge-flip duplex printer mirroring the
    back face left/right relative to the front; `landscape_feed`
    (default True) writes a literal landscape PDF page; False writes a
    `/Rotate`-flagged page that prints onto the paper's natural portrait
    shape -- see this module's docstring for both, including which
    combination is actually physically verified."""
    scheme = signature_plan.scheme
    rows, cols = scheme.grid
    cell_w_pt = scheme.cell_width_in * PT_PER_IN
    cell_h_pt = scheme.cell_height_in * PT_PER_IN
    sheet_w_pt = scheme.sheet_width_in * PT_PER_IN
    sheet_h_pt = scheme.sheet_height_in * PT_PER_IN
    front_grid, back_grid = sheet_panel_layout(scheme.folds)
    # The spine is the shared fold line all leaves in a signature meet at
    # -- for the one implemented multi-leaf scheme (folds=1, a single
    # vertical center fold), that is the sheet's horizontal midpoint.
    spine_x_pt = sheet_w_pt / 2

    with pikepdf.open(source_pdf) as src, pikepdf.new() as out:
        src_pages = src.pages

        def place(page, grid, sig_index, sheet_index, mirror=False):
            leaves = signature_plan.leaves_of(sig_index, sheet_index)
            by_slot = {leaf.sheet_slot: leaf for leaf in leaves}
            for row in range(rows):
                for col in range(cols):
                    src_col, slot = _resolve_cell(cols, row, col, mirror)
                    leaf = by_slot.get(slot)
                    if leaf is None:
                        continue
                    panel = grid[row][src_col]
                    page_num = leaf.recto_page if panel.side == "recto" else leaf.verso_page
                    if page_num is None:
                        continue
                    src_page = src_pages[page_num - 1]
                    src_w = float(src_page.mediabox[2]) - float(src_page.mediabox[0])
                    src_h = float(src_page.mediabox[3]) - float(src_page.mediabox[1])
                    formx = src_page.as_form_xobject()
                    xobj_name = page.add_resource(formx, pikepdf.Name.XObject)
                    cell_x = col * cell_w_pt
                    cell_y = sheet_h_pt - (row + 1) * cell_h_pt
                    a, b, c, d, e, f = _placement_matrix(
                        src_w, src_h, cell_x, cell_y, cell_w_pt, cell_h_pt, panel.rotation
                    )
                    page.contents_add(
                        f"q {a} {b} {c} {d} {e:.3f} {f:.3f} cm {xobj_name} Do Q\n".encode()
                    )
                    if marks and page_overlay:
                        add_page_number(page, page_num, cell_x, cell_y, cell_w_pt, cell_h_pt)

        # If the sheet is logically landscape and the caller hasn't opted
        # into a literal landscape page, build the page exactly as if it
        # were landscape (place()/add_collation_mark()/add_page_number()
        # are completely unaffected, still authoring in the logical
        # sheet_w_pt x sheet_h_pt space) and flag it with the PDF's
        # standard /Rotate attribute instead of swapping the MediaBox --
        # verified to place identical content at identical crop positions
        # (via pdftotext) as the previous content-matrix approach this
        # replaced.
        rotate = not landscape_feed and sheet_w_pt > sheet_h_pt
        # The face a signature's outermost sheet actually shows without
        # unfolding it -- see scheme.py's outward_face(). Collation marks
        # only mean anything drawn there.
        cover_face = outward_face(scheme.folds)

        for sig_index in range(1, signature_plan.signature_count + 1):
            for sheet_index in range(1, signature_plan.sheets_in_signature(sig_index) + 1):
                if sheets_filter is not None and (sig_index, sheet_index) not in sheets_filter:
                    continue
                faces = [("front", front_grid)] + ([("back", back_grid)] if scheme.duplex else [])
                for face_name, grid in faces:
                    page = out.add_blank_page(page_size=(sheet_w_pt, sheet_h_pt))
                    place(page, grid, sig_index, sheet_index, mirror=(duplex_mirror and face_name == "back"))
                    # Once per signature, not once per sheet -- see marks.py.
                    if marks and face_name == cover_face and scheme.duplex and sheet_index == 1:
                        add_collation_mark(
                            page, sheet_h_pt, spine_x_pt, sig_index, signature_plan.signature_count
                        )
                    if rotate:
                        page.Rotate = 90

        outfile.parent.mkdir(parents=True, exist_ok=True)
        out.save(outfile)
