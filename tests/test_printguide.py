"""Tests for the human-readable PRINTING.md generator, in particular its
page map (see printguide._page_map_lines()/render.sheet_face_pages()) --
the aid that lets you check page order flat, before folding, without
opening the rendered PDF and mentally flipping between its front/back
pages."""
from signaturize.impose.binding import load_binding_profile
from signaturize.impose.planner import plan
from signaturize.impose.printguide import render_printing_guide
from signaturize.impose.scheme import PRESETS
from signaturize.typeset.pamphlet import cover_sequence


def test_page_map_shows_pinned_cover_with_a_blank_reverse():
    """The layout the user asked to recheck, matching the original
    pamphlet pipeline's own proven layout bit-for-bit (see scheme.py's
    sheet_panel_layout() docstring): title page on sheet 1's back-west,
    reverse blank; page 2 in that same slot on the next sheet in, page 3
    directly behind it."""
    result = plan(16, PRESETS["folio"], load_binding_profile("pamphlet"), content_sequence=cover_sequence(16))
    guide = render_printing_guide("Test Book", result, "test-book-imposed.pdf")

    assert "| 1 (outermost) | blank | blank | 1 | blank |" in guide
    assert "| 2 | 3 | 16 | 2 | blank |" in guide
    assert "| 5 (innermost) | 9 | 10 | 8 | 11 |" in guide


def test_page_map_for_single_leaf_scheme_has_one_column_per_face():
    from dataclasses import replace

    result = plan(4, replace(PRESETS["folio"], folds=0), load_binding_profile("perfect-bound-leaves"))
    guide = render_printing_guide("Test Book", result, "test-book-imposed.pdf")
    assert "## Page map" in guide
    assert "| sheet | front col 1 | back col 1 |" in guide
    assert "| 1 (outermost) | 1 | 2 |" in guide


def test_page_map_always_shows_the_unmirrored_physical_result():
    """The page map has no duplex_mirror of its own to set: it always
    shows the final, correctly-printed physical sheet (duplex_mirror=
    False's values), regardless of whatever duplex_mirror render() is
    actually called with for the PDF file -- because a correctly
    configured duplex_mirror's whole job is to make the physical result
    match that unmirrored layout (the file's own columns are
    deliberately pre-swapped to compensate for the printer's own
    mirroring; see printguide._page_map_lines()'s docstring). This is
    what the title ending up on physical-east here, not matching the raw
    PDF file's own back-face column (see
    test_sheet_face_pages_pinned_cover_layout in test_render.py), is
    about."""
    from signaturize.impose.render import sheet_face_pages

    content_sequence = [1, None] + list(range(2, 8))
    result = plan(7, PRESETS["folio"], load_binding_profile("pamphlet"), content_sequence=content_sequence)
    guide = render_printing_guide("Test Book", result, "x.pdf")

    for sheet in range(1, result.sheets_in_signature(1) + 1):
        expected = sheet_face_pages(result, 1, sheet, duplex_mirror=False)
        for face in ("front", "back"):
            for page in expected[face]:
                if page is not None:
                    assert str(page) in guide
