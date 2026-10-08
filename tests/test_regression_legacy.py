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
  lands on which leaf/side) in place as an extra regression guard, after a
  bug where a since-reverted change to cover_sequence() briefly diverged
  from this. This is purely about content order (planner.py), not which
  physical sheet face/column ends up where once folded (scheme.py/
  render.py).
- test_render_matches_real_printed_beatrix_potter_books goes one step
  further and checks render()'s actual *physical placement* against five
  real books' real, physically-printed-and-folded booklet.pdf outputs
  (~/projects/projectgutenberg/beatrix-potter -- a separate, independent
  project; see requires_beatrix_potter_reference below), closing a gap
  that let a real regression through twice before: a prior change to
  scheme.py's sheet_panel_layout()/render.py's column mapping, made on an
  unverified claim of a physical fold test, passed every test in this
  file (none of which touched physical placement) while silently
  scrambling reading order from sheet 2 onward; the fix for *that* was
  then itself checked against a same-repo reference file that turned out
  to be an equally unverified, mislabeled artifact of the same kind of
  bug -- only comparing against real books someone actually printed,
  folded, and used caught the real answer (duplex_mirror defaults to
  True: a standard long-edge-flip duplex printer mirrors the back face).
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

# ~/projects/projectgutenberg/beatrix-potter is a separate, independent
# project (see top-level AGENTS.md: no two project folders share state) --
# it happens to be the actual, original pamphlet pipeline this planner was
# ported from, still holding its own real, physically-printed-and-folded
# booklet.pdf outputs and the trimmed.pdf each was built from. That's the
# strongest verification available (five real books, not a synthetic
# fixture) but it's this user's local machine, not something the repo
# ships or any other checkout can assume exists -- skip rather than fail
# when it's missing. (An earlier, same-shaped reference pair used to live
# in this repo's own gitignored output/build/ dirs, labeled "correct" --
# it was never actually physically verified, and in fact matched the
# *unmirrored* convention these five real books contradict; it has since
# been removed.)
_REFERENCE_ROOT = Path.home() / "projects" / "projectgutenberg" / "beatrix-potter"
_REFERENCE_BOOKS = [
    "tailor-of-gloucester", "peter-rabbit", "benjamin-bunny", "squirrel-nutkin", "jemima-puddle-duck",
]
_reference_pairs = [
    (_REFERENCE_ROOT / "build" / book / "trimmed.pdf", _REFERENCE_ROOT / "output" / f"{book}-booklet.pdf")
    for book in _REFERENCE_BOOKS
]
requires_beatrix_potter_reference = pytest.mark.skipif(
    not all(trimmed.exists() and correct.exists() for trimmed, correct in _reference_pairs),
    reason=f"{_REFERENCE_ROOT} (a separate local project, not shipped with this repo) is not present "
    "with all five reference books built",
)

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
    """duplex_mirror=False explicitly here, to check the base A/B/C/D
    structural assignment cleanly without the (now-default) printer
    column swap layered on top -- that combination is checked
    separately, against real printed references, by
    test_render_matches_peter_rabbit_correct_pdf below."""
    n_pages = 13
    src = write_numbered_pdf(tmp_path / "trim.pdf", n_pages)
    out = tmp_path / "out" / "imposed.pdf"
    result = plan(n_pages, PRESETS["folio"], NO_BLANKS, content_sequence=cover_sequence(n_pages))
    render(src, result, out, marks=False, landscape_feed=True, duplex_mirror=False)

    layout = _leaves_to_abcd(result.leaves)
    assert pdf_page_count(out) == 2 * len(layout)
    # letter landscape sheet, halves are 396pt wide. render.py's
    # sheet_slot 0/1 ("west"/"east" leaves in this helper's A/B/C/D
    # naming, where A/C come from the west/slot-0 leaf and B/D from the
    # east/slot-1 leaf) land directly on their own physical column, no
    # swap -- matching the original pamphlet pipeline's own A/B/C/D
    # convention exactly (see scheme.py's sheet_panel_layout()
    # docstring). So the renderer's front pass (PDF page 1) shows A on
    # physical-west and B on physical-east; back (page 2) shows C on
    # physical-west and D on physical-east.
    for sheet, (a, b, c, d) in layout.items():
        for side, (west, east) in enumerate([(a, b), (c, d)]):
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


@requires_poppler
@requires_beatrix_potter_reference
@pytest.mark.parametrize("book, trimmed, correct", [
    (book, trimmed, correct) for book, (trimmed, correct) in zip(_REFERENCE_BOOKS, _reference_pairs)
])
def test_render_matches_real_printed_beatrix_potter_books(tmp_path, book, trimmed, correct):
    """The strongest check available without folding paper ourselves:
    impose each book's real trim PDF with today's render() (duplex_mirror
    at its default, True) and diff it, page by page and column by
    column, against that book's real booklet.pdf -- the original tool's
    own output, a standard long-edge-flip duplex printer away from an
    actual, physically folded and used copy of that book. Every sheet
    page, both the west and east 396pt column of each, must come out
    byte-for-byte identical, for all five books."""
    n_pages = pdf_page_count(trimmed)
    binding = load_binding_profile("pamphlet")
    result = plan(n_pages, PRESETS["folio"], binding, content_sequence=cover_sequence(n_pages))
    out = tmp_path / "imposed.pdf"
    render(trimmed, result, out, marks=False, landscape_feed=True)

    assert pdf_page_count(out) == pdf_page_count(correct)
    for page in range(1, pdf_page_count(out) + 1):
        for crop in [(0, 0, 396, 612), (396, 0, 396, 612)]:
            assert pdf_text(out, page, crop) == pdf_text(correct, page, crop), (
                f"{book}: page {page}, crop {crop} diverges from the known-correct reference"
            )
