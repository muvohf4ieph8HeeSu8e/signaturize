"""Regression guards for the original single-signature folio pamphlet
behaviour, so later milestones can prove they haven't changed it.

- compute_layout() is pinned to golden values captured before the package
  restructure (tests/golden/legacy_nested_folio_layout.json).
- The PDF-level test imposes a synthetic numbered PDF and checks, with
  pdftotext, that every half-sheet holds the trim page compute_layout()
  says it should.
"""
import json
from pathlib import Path

import pytest

from conftest import pdf_text, requires_latex, requires_poppler, write_numbered_pdf
from signaturize.config import load_config
from signaturize.impose import nested_folio
from signaturize.tools import pdf_page_count

GOLDEN = json.loads((Path(__file__).parent / "golden" / "legacy_nested_folio_layout.json").read_text())


@pytest.mark.parametrize("n_pages", sorted(GOLDEN, key=int))
def test_compute_layout_matches_golden(n_pages):
    expected = {int(sheet): tuple(slots) for sheet, slots in GOLDEN[n_pages].items()}
    assert nested_folio.compute_layout(int(n_pages)) == expected


@requires_poppler
@requires_latex
def test_imposed_halves_hold_the_expected_trim_pages(tmp_path):
    n_pages = 13
    src = write_numbered_pdf(tmp_path / "trim.pdf", n_pages)
    out = tmp_path / "out" / "imposed.pdf"
    nested_folio.build(src, out, None, load_config(None))

    layout = nested_folio.compute_layout(n_pages)
    assert pdf_page_count(out) == 2 * len(layout)
    # letter landscape sheet, halves are 396pt wide
    for sheet, (a, b, c, d) in layout.items():
        for side, (west, east) in enumerate([(a, b), (c, d)]):
            page = 2 * (sheet - 1) + side + 1
            assert pdf_text(out, page, (0, 0, 396, 612)) == (str(west) if west else "")
            assert pdf_text(out, page, (396, 0, 396, 612)) == (str(east) if east else "")

    # the scratch build files must not be left next to the output
    assert sorted(p.name for p in out.parent.iterdir()) == ["imposed.pdf"]
