"""Regression guards for the original single-signature folio pamphlet
behaviour, so later milestones can prove they haven't changed it.

- The original pamphlet pipeline's nested-folio layout is pinned to golden
  values captured before the package restructure
  (tests/golden/legacy_nested_folio_layout.json), re-derived via the
  general planner.plan() + typeset.pamphlet.cover_sequence() (the
  content-layer pin that replaces the original's hard-coded cover/blank
  slots) instead of the since-removed impose/nested_folio.py.
  cover_sequence() pins only the front cover (page 1 + a forced blank on
  its own reverse) -- the same, and only, pin the original algorithm ever
  made; nothing is pinned at the signature's other end, which is left to
  plan()'s own general padding, exactly like the original.
- The PDF-level test imposes a synthetic numbered PDF via impose.render.render()
  and checks, with pdftotext, that every half-sheet holds the trim page
  the plan says it should.
- test_cover_sequence_matches_peter_rabbit_golden_layout pins the original
  tool's own 29-page "Peter Rabbit" *content-sequencing* (which trim page
  lands on which leaf/side -- see output/peter-rabbit-booklet-correct.pdf)
  in place as an extra regression guard, after a bug where a
  since-reverted change to cover_sequence() briefly diverged from this.
  This is purely about content order, not which physical sheet face ends
  up outward once folded -- a real print-and-fold test showed that file's
  front cover landing on the *inside*, which is what prompted the
  front/back swap in scheme.py's sheet_panel_layout() (see its docstring);
  this test is unaffected by that fix, since it never touches render.py.
"""
import json
from pathlib import Path

import pytest

from conftest import pdf_text, requires_poppler, write_numbered_pdf
from signaturize.impose.binding import BindingProfile, load_binding_profile
from signaturize.impose.planner import Leaf, plan
from signaturize.impose.render import render
from signaturize.impose.scheme import PRESETS
from signaturize.tools import pdf_page_count
from signaturize.typeset.pamphlet import cover_sequence

GOLDEN = json.loads((Path(__file__).parent / "golden" / "legacy_nested_folio_layout.json").read_text())

# Reproduces the original pipeline's unbounded single signature (no facing
# blanks, nest everything into one signature regardless of size).
NO_BLANKS = BindingProfile(leading_blank_leaves=0, trailing_blank_leaves=0, nest_preferred=999, nest_max=999)


def _leaves_to_abcd(leaves: tuple[Leaf, ...]) -> dict[int, tuple[int | None, int | None, int | None, int | None]]:
    """Leaf(sheet_slot=0/1 west/east, recto/verso) pairs -> the legacy
    {sheet: (A, B, C, D)} shape: A=west's verso, B=east's recto, C=west's
    recto, D=east's verso -- the original pamphlet pipeline's own fixed
    naming for these four positions, independent of which physical sheet
    face (front/back, i.e. which print pass) they land on in the general
    renderer. This helper is purely about matching planner.py's
    content-sequencing to the legacy golden data
    (tests/golden/legacy_nested_folio_layout.json); which of A/B vs C/D
    ends up on the *outward*-facing printed pass is scheme.py's
    sheet_panel_layout() concern, exercised separately in
    test_imposed_halves_hold_the_expected_trim_pages below and in
    tests/test_render.py."""
    by_sheet: dict[int, dict[int, Leaf]] = {}
    for leaf in leaves:
        by_sheet.setdefault(leaf.sheet_index, {})[leaf.sheet_slot] = leaf
    out = {}
    for sheet, slots in by_sheet.items():
        west, east = slots[0], slots[1]
        out[sheet] = (west.verso_page, east.recto_page, west.recto_page, east.verso_page)
    return out


@pytest.mark.parametrize("n_pages", sorted(GOLDEN, key=int))
def test_plan_matches_golden(n_pages):
    n_pages = int(n_pages)
    expected = {int(sheet): tuple(slots) for sheet, slots in GOLDEN[str(n_pages)].items()}
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS, content_sequence=cover_sequence(n_pages))
    assert _leaves_to_abcd(result.leaves) == expected


@requires_poppler
def test_imposed_halves_hold_the_expected_trim_pages(tmp_path):
    n_pages = 13
    src = write_numbered_pdf(tmp_path / "trim.pdf", n_pages)
    out = tmp_path / "out" / "imposed.pdf"
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS, content_sequence=cover_sequence(n_pages))
    render(src, result, out, marks=False, landscape_feed=True)

    layout = _leaves_to_abcd(result.leaves)
    assert pdf_page_count(out) == 2 * len(layout)
    # letter landscape sheet, halves are 396pt wide. A physical fold test
    # showed render.py's sheet_slot 0/1 ("west"/"east" leaves in this
    # helper's A/B/C/D naming, where A/C come from the west/slot-0 leaf
    # and B/D from the east/slot-1 leaf) land on the *opposite* physical
    # column from a naive column==slot mapping -- see render.py's
    # docstring. So the renderer's front pass (PDF page 1, the
    # outward-facing one once folded) shows D on physical-west and C on
    # physical-east; back (page 2) shows B on physical-west and A on
    # physical-east.
    for sheet, (a, b, c, d) in layout.items():
        for side, (west, east) in enumerate([(d, c), (b, a)]):
            page = 2 * (sheet - 1) + side + 1
            assert pdf_text(out, page, (0, 0, 396, 612)) == (str(west) if west else "")
            assert pdf_text(out, page, (396, 0, 396, 612)) == (str(east) if east else "")


def test_cover_sequence_matches_peter_rabbit_golden_layout():
    """Pin the real, physically-printed-and-confirmed-correct 29-page
    Peter Rabbit example (output/peter-rabbit-booklet-correct.pdf,
    generated by the original tool from build/peter-rabbit/) in place:
    sheet 1 (outermost) is blank except for the title on its recto/front
    cover, and the colophon (page 29) isn't pinned anywhere -- it just
    falls on sheet 2 naturally, exactly where the original tool put it."""
    n_pages = 29
    binding = load_binding_profile("pamphlet")  # the real CLI default, not NO_BLANKS
    result = plan(n_pages, PRESETS["folio"], binding, content_sequence=cover_sequence(n_pages))
    abcd = _leaves_to_abcd(result.leaves)
    golden = {int(sheet): tuple(slots) for sheet, slots in GOLDEN["29"].items()}
    assert abcd[1] == golden[1] == (None, None, 1, None)
    assert abcd[2] == golden[2] == (3, 28, 2, 29)
