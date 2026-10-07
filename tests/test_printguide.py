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


def test_page_map_shows_pinned_cover_on_the_right_with_a_blank_reverse():
    """The exact layout the user asked to recheck: title page right,
    outward, reverse blank; page 2 in that same slot on the next sheet
    in, page 3 on its reverse."""
    result = plan(16, PRESETS["folio"], load_binding_profile("pamphlet"), content_sequence=cover_sequence(16))
    guide = render_printing_guide("Test Book", result, "test-book-imposed.pdf")

    assert "| 1 (outermost) | blank | 1 | blank | blank |" in guide
    assert "| 2 | blank | 2 | 16 | 3 |" in guide
    assert "| 5 (innermost) | 11 | 8 | 10 | 9 |" in guide


def test_page_map_for_single_leaf_scheme_has_one_column_per_face():
    from dataclasses import replace

    result = plan(4, replace(PRESETS["folio"], folds=0), load_binding_profile("perfect-bound-leaves"))
    guide = render_printing_guide("Test Book", result, "test-book-imposed.pdf")
    assert "## Page map" in guide
    assert "| sheet | front col 1 | back col 1 |" in guide
    assert "| 1 (outermost) | 1 | 2 |" in guide


def test_page_map_respects_duplex_mirror():
    content_sequence = [1, None] + list(range(2, 8))
    result = plan(7, PRESETS["folio"], load_binding_profile("pamphlet"), content_sequence=content_sequence)
    normal = render_printing_guide("Test Book", result, "x.pdf", duplex_mirror=False)
    mirrored = render_printing_guide("Test Book", result, "x.pdf", duplex_mirror=True)
    assert normal != mirrored
