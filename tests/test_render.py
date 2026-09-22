"""PDF-level tests for the general imposition renderer: every source page
ends up on the sheet/half/face the plan says it should."""
from dataclasses import replace

import pytest

from conftest import pdf_text, requires_poppler, write_numbered_pdf
from signaturize.impose.binding import BindingProfile, load_binding_profile
from signaturize.impose.planner import plan
from signaturize.impose.render import render
from signaturize.impose.scheme import PRESETS
from signaturize.tools import pdf_page_count

NO_BLANKS = BindingProfile(leading_blank_leaves=0, trailing_blank_leaves=0, nest_preferred=8, nest_max=16)


@requires_poppler
def test_folio_sheet_halves_hold_the_planned_pages(tmp_path):
    n_pages = 29
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS)
    out = tmp_path / "imposed.pdf"
    render(src, result, out, marks=False)

    assert pdf_page_count(out) == 2 * result.total_sheets()
    for sig in range(1, result.signature_count + 1):
        for sheet in range(1, result.sheets_in_signature(sig) + 1):
            leaves = result.leaves_of(sig, sheet)
            west = next(leaf for leaf in leaves if leaf.sheet_slot == 0)
            east = next(leaf for leaf in leaves if leaf.sheet_slot == 1)
            front_page = 2 * (sheet - 1) + 1
            back_page = front_page + 1
            # front-west = west's verso, front-east = east's recto
            assert pdf_text(out, front_page, (0, 0, 396, 612)) == (str(west.verso_page) if west.verso_page else "")
            assert pdf_text(out, front_page, (396, 0, 396, 612)) == (str(east.recto_page) if east.recto_page else "")
            # back-west = west's recto, back-east = east's verso
            assert pdf_text(out, back_page, (0, 0, 396, 612)) == (str(west.recto_page) if west.recto_page else "")
            assert pdf_text(out, back_page, (396, 0, 396, 612)) == (str(east.verso_page) if east.verso_page else "")


@requires_poppler
def test_single_leaf_simplex_writes_only_recto_pages(tmp_path):
    n_pages = 6
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    binding = load_binding_profile("perfect-bound-leaves")
    scheme = replace(PRESETS["single-leaf"], duplex=False)
    result = plan(n_pages, scheme, binding)
    out = tmp_path / "imposed.pdf"
    render(src, result, out, marks=False)

    assert pdf_page_count(out) == result.total_sheets()  # one face per sheet, no back
    for i, leaf in enumerate(sorted(result.leaves, key=lambda l: l.signature_index), start=1):
        assert pdf_text(out, i, (0, 0, 396, 612)) == str(leaf.recto_page)


@requires_poppler
def test_collation_marks_present_once_per_signature_back_face(tmp_path):
    n_pages = 200
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    binding = BindingProfile(nest_preferred=4, nest_max=6)
    result = plan(n_pages, PRESETS["folio"], binding)
    out = tmp_path / "imposed.pdf"
    render(src, result, out, marks=True)  # must not raise across multiple signatures
    assert pdf_page_count(out) == 2 * result.total_sheets()


@requires_poppler
def test_source_larger_than_cell_raises_clear_error(tmp_path):
    src = write_numbered_pdf(tmp_path / "src.pdf", 4, width_pt=1000, height_pt=1000)
    result = plan(4, PRESETS["folio"], NO_BLANKS)
    with pytest.raises(ValueError, match="larger than"):
        render(src, result, tmp_path / "imposed.pdf", marks=False)


@requires_poppler
def test_sheets_filter_renders_only_the_requested_sheet(tmp_path):
    n_pages = 100
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    result = plan(n_pages, PRESETS["folio"], load_binding_profile("pamphlet"))
    out = tmp_path / "test-sheet.pdf"
    render(src, result, out, sheets_filter={(1, 1)}, marks=False)
    assert pdf_page_count(out) == 2
