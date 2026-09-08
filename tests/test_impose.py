"""Unit tests for the saddle-stitch single-signature imposition math.

This is the highest-value test surface in the package: compute_layout() is
the pure function future multi-signature support will build on, so its
invariants need to hold for a wide range of page counts.
"""
import pytest

from signaturize.impose import compute_layout


@pytest.mark.parametrize("n_pages", [1, 2, 3, 4, 5, 8, 9, 16, 17, 33, 50])
def test_every_trim_page_placed_exactly_once(n_pages):
    layout = compute_layout(n_pages)
    placed = [page for slots in layout.values() for page in slots if page is not None]
    assert sorted(placed) == list(range(1, n_pages + 1))


@pytest.mark.parametrize("n_pages", [1, 2, 3, 8, 17, 33])
def test_page_one_is_sheet_one_slot_c(n_pages):
    layout = compute_layout(n_pages)
    _a, _b, c, _d = layout[1]
    assert c == 1


@pytest.mark.parametrize("n_pages", [1, 2, 3, 8, 17, 33])
def test_sheet_one_slot_a_is_always_blank(n_pages):
    layout = compute_layout(n_pages)
    a, _b, _c, _d = layout[1]
    assert a is None


@pytest.mark.parametrize("n_pages", [1, 5, 9, 16, 33])
def test_sheet_count_is_minimal(n_pages):
    layout = compute_layout(n_pages)
    total_sheets = len(layout)
    # enough slots for all remaining content (2 fixed cover slots used already)
    assert 4 * total_sheets - 2 >= n_pages - 1
    # and one fewer sheet would not have been enough
    if total_sheets > 1:
        assert 4 * (total_sheets - 1) - 2 < n_pages - 1
