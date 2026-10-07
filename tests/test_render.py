"""PDF-level tests for the general imposition renderer: every source page
ends up on the sheet/half/face the plan says it should."""
from dataclasses import replace

import pytest

from conftest import pdf_page_size_in, pdf_text, requires_poppler, write_numbered_pdf
from signaturize.impose.binding import BindingProfile, load_binding_profile
from signaturize.impose.planner import plan
from signaturize.impose.render import render, sheet_face_pages
from signaturize.impose.scheme import PRESETS
from signaturize.tools import pdf_page_count

NO_BLANKS = BindingProfile(leading_blank_leaves=0, trailing_blank_leaves=0, nest_preferred=8, nest_max=16)


@requires_poppler
def test_folio_sheet_halves_hold_the_planned_pages(tmp_path):
    n_pages = 29
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS)
    out = tmp_path / "imposed.pdf"
    render(src, result, out, marks=False, landscape_feed=True)

    assert pdf_page_count(out) == 2 * result.total_sheets()
    for sig in range(1, result.signature_count + 1):
        for sheet in range(1, result.sheets_in_signature(sig) + 1):
            leaves = result.leaves_of(sig, sheet)
            west = next(leaf for leaf in leaves if leaf.sheet_slot == 0)
            east = next(leaf for leaf in leaves if leaf.sheet_slot == 1)
            front_page = 2 * (sheet - 1) + 1
            back_page = front_page + 1
            # A physical fold test showed sheet_slot 0/1 ("west"/"east")
            # land on the *opposite* physical column from a naive
            # column==slot mapping -- see render.py's docstring. So the
            # physical-west cell (x=0) holds the slot-1 ("east") leaf, and
            # the physical-east cell (x=396) holds the slot-0 ("west")
            # leaf. front-physical-west = east's verso, front-physical-east
            # = west's recto (front is the outward-facing pass once
            # folded -- see scheme.py).
            assert pdf_text(out, front_page, (0, 0, 396, 612)) == (str(east.verso_page) if east.verso_page else "")
            assert pdf_text(out, front_page, (396, 0, 396, 612)) == (str(west.recto_page) if west.recto_page else "")
            # back-physical-west = east's recto, back-physical-east = west's verso
            assert pdf_text(out, back_page, (0, 0, 396, 612)) == (str(east.recto_page) if east.recto_page else "")
            assert pdf_text(out, back_page, (396, 0, 396, 612)) == (str(west.verso_page) if west.verso_page else "")


@requires_poppler
def test_folio_default_rotates_content_into_a_portrait_page(tmp_path):
    """The new default (landscape_feed=False): the physical PDF page
    stays portrait-shaped (the paper's own natural orientation) and the
    whole folio layout rotates 90 degrees into it as one rigid unit --
    west content (logical left half) lands in the top half of the
    portrait page, east content (logical right half) in the bottom half.
    Same physical sheet as test_folio_sheet_halves_hold_the_planned_pages
    above, just encoded as a rotated-content portrait page instead of a
    literal landscape one."""
    n_pages = 4
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS)
    out = tmp_path / "imposed.pdf"
    render(src, result, out, marks=False)  # landscape_feed defaults to False

    assert pdf_page_size_in(out) == (8.5, 11.0)  # portrait, not the 11x8.5 landscape sheet
    leaves = result.leaves_of(1, 1)
    west = next(leaf for leaf in leaves if leaf.sheet_slot == 0)
    east = next(leaf for leaf in leaves if leaf.sheet_slot == 1)
    top, bottom = (0, 0, 612, 396), (0, 396, 612, 396)
    # Physical-west (top, since the whole layout is rotated 90 degrees
    # here) holds the slot-1 ("east") leaf, and physical-east (bottom)
    # holds the slot-0 ("west") leaf -- see render.py's docstring and
    # test_folio_sheet_halves_hold_the_planned_pages above.
    # front: east's verso on top, west's recto on bottom
    assert pdf_text(out, 1, top) == str(east.verso_page)
    assert pdf_text(out, 1, bottom) == str(west.recto_page)
    # back: east's recto on top, west's verso on bottom
    assert pdf_text(out, 2, top) == str(east.recto_page)
    assert pdf_text(out, 2, bottom) == str(west.verso_page)


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
def test_collation_marks_present_once_per_signature_not_once_per_sheet(tmp_path):
    n_pages = 200
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    binding = BindingProfile(nest_preferred=4, nest_max=6)
    result = plan(n_pages, PRESETS["folio"], binding)
    out = tmp_path / "imposed.pdf"
    render(src, result, out, marks=True, landscape_feed=True)
    assert pdf_page_count(out) == 2 * result.total_sheets()
    assert result.signature_count > 1  # otherwise this test can't distinguish the two

    import pikepdf
    with pikepdf.open(out) as pdf:
        pages_with_mark = 0
        for page in pdf.pages:
            page.contents_coalesce()
            if b" re f " in page.Contents.read_bytes():
                pages_with_mark += 1
    # one mark per signature (its outermost sheet's front/outward face),
    # not one per sheet -- see marks.py/render.py for why.
    assert pages_with_mark == result.signature_count


@requires_poppler
def test_page_numbers_label_every_panel(tmp_path):
    n_pages = 4
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS)
    out = tmp_path / "imposed.pdf"
    render(src, result, out, marks=True, landscape_feed=True)  # marks=True (default) draws page numbers

    leaves = result.leaves_of(1, 1)
    west = next(leaf for leaf in leaves if leaf.sheet_slot == 0)
    east = next(leaf for leaf in leaves if leaf.sheet_slot == 1)
    bottom_strip_west, bottom_strip_east = (0, 590, 396, 22), (396, 590, 396, 22)
    # physical-west holds the slot-1 ("east") leaf, physical-east holds
    # the slot-0 ("west") leaf (same mapping proven elsewhere in this file)
    # front: east's verso, west's recto
    assert pdf_text(out, 1, bottom_strip_west) == str(east.verso_page)
    assert pdf_text(out, 1, bottom_strip_east) == str(west.recto_page)
    # back: east's recto, west's verso
    assert pdf_text(out, 2, bottom_strip_west) == str(east.recto_page)
    assert pdf_text(out, 2, bottom_strip_east) == str(west.verso_page)


@requires_poppler
def test_marks_false_omits_page_numbers_too(tmp_path):
    n_pages = 4
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS)
    out = tmp_path / "imposed.pdf"
    render(src, result, out, marks=False, landscape_feed=True)
    # bottom strip should be empty -- no page-number label -- when marks=False
    assert pdf_text(out, 1, (0, 590, 396, 22)) == ""


@requires_poppler
def test_source_larger_than_cell_raises_clear_error(tmp_path):
    src = write_numbered_pdf(tmp_path / "src.pdf", 4, width_pt=1000, height_pt=1000)
    result = plan(4, PRESETS["folio"], NO_BLANKS)
    with pytest.raises(ValueError, match="larger than"):
        render(src, result, tmp_path / "imposed.pdf", marks=False)


@requires_poppler
def test_duplex_mirror_swaps_back_face_columns_only(tmp_path):
    n_pages = 4
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS)
    out_normal = tmp_path / "normal.pdf"
    out_mirror = tmp_path / "mirror.pdf"
    render(src, result, out_normal, marks=False, landscape_feed=True)
    render(src, result, out_mirror, marks=False, duplex_mirror=True, landscape_feed=True)

    # front face (page 1) unaffected
    assert pdf_text(out_normal, 1, (0, 0, 396, 612)) == pdf_text(out_mirror, 1, (0, 0, 396, 612))
    assert pdf_text(out_normal, 1, (396, 0, 396, 612)) == pdf_text(out_mirror, 1, (396, 0, 396, 612))
    # back face (page 2) west/east swapped
    assert pdf_text(out_normal, 2, (0, 0, 396, 612)) == pdf_text(out_mirror, 2, (396, 0, 396, 612))
    assert pdf_text(out_normal, 2, (396, 0, 396, 612)) == pdf_text(out_mirror, 2, (0, 0, 396, 612))


@requires_poppler
def test_sheets_filter_renders_only_the_requested_sheet(tmp_path):
    n_pages = 100
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    result = plan(n_pages, PRESETS["folio"], load_binding_profile("pamphlet"))
    out = tmp_path / "test-sheet.pdf"
    render(src, result, out, sheets_filter={(1, 1)}, marks=False)
    assert pdf_page_count(out) == 2


@requires_poppler
def test_sheet_face_pages_matches_what_render_actually_draws(tmp_path):
    """sheet_face_pages() is a pure-data re-derivation of render()'s own
    placement, used by printguide.py's page map (see its own docstring)
    -- so it must never drift from what render() actually puts on the
    page. Cross-checked here against the same text-extraction assertions
    test_folio_sheet_halves_hold_the_planned_pages uses, for both a plain
    sequential layout and a pinned-cover one (None in the middle of the
    content)."""
    n_pages = 29
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS)
    out = tmp_path / "imposed.pdf"
    render(src, result, out, marks=False, landscape_feed=True)

    for sig in range(1, result.signature_count + 1):
        for sheet in range(1, result.sheets_in_signature(sig) + 1):
            front_page = 2 * (sheet - 1) + 1
            back_page = front_page + 1
            pages = sheet_face_pages(result, sig, sheet)
            assert pdf_text(out, front_page, (0, 0, 396, 612)) == (str(pages["front"][0]) if pages["front"][0] else "")
            assert pdf_text(out, front_page, (396, 0, 396, 612)) == (str(pages["front"][1]) if pages["front"][1] else "")
            assert pdf_text(out, back_page, (0, 0, 396, 612)) == (str(pages["back"][0]) if pages["back"][0] else "")
            assert pdf_text(out, back_page, (396, 0, 396, 612)) == (str(pages["back"][1]) if pages["back"][1] else "")


def test_sheet_face_pages_pinned_cover_layout():
    """The exact shape typeset.pamphlet.cover_sequence() produces (16
    content pages, the pamphlet binding profile -- the same inputs the
    README's worked example uses): title (page 1) on the physical-right
    of sheet 1's front face (the face that ends up outward once folded)
    with a forced blank beside it and a blank reverse, and page 2 landing
    in that same physical-right slot on the next sheet in, with page 3 on
    its reverse -- the layout the user actually asked to recheck. Cross-
    checked against this exact book's rendered PDF via pdftotext before
    being pinned here."""
    from signaturize.typeset.pamphlet import cover_sequence

    result = plan(16, PRESETS["folio"], load_binding_profile("pamphlet"), content_sequence=cover_sequence(16))
    assert result.sheets_in_signature(1) == 5

    sheet1 = sheet_face_pages(result, 1, 1)
    assert sheet1["front"] == [None, 1]       # title, physical-right, outward
    assert sheet1["back"] == [None, None]     # title's reverse: blank

    sheet2 = sheet_face_pages(result, 1, 2)
    assert sheet2["front"][1] == 2            # page 2, same physical-right slot as the title
    assert sheet2["back"][1] == 3             # page 3, its reverse
