"""Render a SignaturePlan against a source PDF into print-ready sheets,
using pikepdf: each source page becomes a Form XObject placed by an affine
matrix into its panel's cell, with a 180-degree rotation where the fold
simulator (scheme.py) calls for one. One PDF page is written per sheet
face (front, then back if duplex) -- page order is already duplex-ready
print order.
"""
from __future__ import annotations

from pathlib import Path

import pikepdf

from .marks import add_collation_mark, add_slug_line
from .planner import SignaturePlan
from .scheme import sheet_panel_layout

PT_PER_IN = 72.0


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
    slug_prefix: str = "",
) -> None:
    """Write imposed sheets to `outfile`. If `sheets_filter` is given, only
    those (signature_index, sheet_index) pairs are rendered (e.g. for a
    one-sheet physical test print)."""
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

        def place(page, grid, sig_index, sheet_index):
            leaves = signature_plan.leaves_of(sig_index, sheet_index)
            by_slot = {leaf.sheet_slot: leaf for leaf in leaves}
            for row in range(rows):
                for col in range(cols):
                    slot = row * cols + col
                    leaf = by_slot.get(slot)
                    if leaf is None:
                        continue
                    panel = grid[row][col]
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

        for sig_index in range(1, signature_plan.signature_count + 1):
            for sheet_index in range(1, signature_plan.sheets_in_signature(sig_index) + 1):
                if sheets_filter is not None and (sig_index, sheet_index) not in sheets_filter:
                    continue
                faces = [("front", front_grid)] + ([("back", back_grid)] if scheme.duplex else [])
                for face_name, grid in faces:
                    page = out.add_blank_page(page_size=(sheet_w_pt, sheet_h_pt))
                    place(page, grid, sig_index, sheet_index)
                    if marks and face_name == "back" and scheme.duplex:
                        add_collation_mark(
                            page, sheet_h_pt, spine_x_pt, sig_index, signature_plan.signature_count
                        )
                    if marks:
                        label = f"{slug_prefix}sig {sig_index}/{signature_plan.signature_count} " \
                                f"sheet {sheet_index}/{signature_plan.sheets_in_signature(sig_index)} {face_name}"
                        add_slug_line(page, label)

        outfile.parent.mkdir(parents=True, exist_ok=True)
        out.save(outfile)
