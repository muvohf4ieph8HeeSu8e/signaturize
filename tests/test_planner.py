"""Tests for the general signature planner.

The highest-risk part of planner.py is the folds=1 nested-telescoping
leaf order -- it must exactly match impose/nested_folio.py's
compute_layout(), which is proven correct (it produces the physical
booklets in build/*) and is pinned to golden values in
tests/test_regression_legacy.py.
test_nested_folio_matches_hand_derived_legacy_slot_order below checks the
planner against a slot order transcribed directly from compute_layout's
own traversal code (sheet1.C, sheet1.A, sheet2.C, sheet2.A, ...,
sheetN.C, sheetN.A, sheetN.B, sheetN.D, ..., sheet1.B, sheet1.D), minus
compute_layout's two pamphlet-specific pins (a forced-blank second page
and a pinned cover page) -- those are a content-layer decision belonging
to typeset.py, not general imposition, so they're intentionally excluded
here; what's checked is the general nested slot *order* the two
implementations share.
"""
import pytest

from signaturize.impose.binding import BindingProfile, list_binding_profiles, load_binding_profile
from signaturize.impose.planner import plan
from signaturize.impose.scheme import PRESETS, Scheme

NO_BLANKS = BindingProfile(leading_blank_leaves=0, trailing_blank_leaves=0, nest_preferred=999, nest_max=999)


def _reference_folio_slot_order(n_sheets):
    """(sheet_index, sheet_slot) in fill order for one folio signature,
    slot 0 = west leaf (C, A in impose/nested_folio.py's naming), slot 1 =
    east leaf (B, D)."""
    order = [(s, 0) for s in range(1, n_sheets + 1)]
    order += [(s, 1) for s in range(n_sheets, 0, -1)]
    return order


def test_nested_folio_matches_hand_derived_legacy_slot_order():
    for n_sheets in (1, 2, 3, 5, 8):
        content_pages = 4 * n_sheets
        result = plan(content_pages, PRESETS["folio"], NO_BLANKS)
        assert result.signature_count == 1
        assert result.padding_pages == 0

        page = 1
        for sheet_index, slot in _reference_folio_slot_order(n_sheets):
            leaf = next(
                leaf for leaf in result.leaves
                if leaf.sheet_index == sheet_index and leaf.sheet_slot == slot
            )
            assert (leaf.recto_page, leaf.verso_page) == (page, page + 1)
            page += 2


@pytest.mark.parametrize("content_pages", [1, 2, 3, 7, 16, 29, 33, 100, 257])
@pytest.mark.parametrize("scheme_name", ["single-leaf", "folio"])
def test_every_content_page_placed_exactly_once(content_pages, scheme_name):
    binding = load_binding_profile("pamphlet")
    result = plan(content_pages, PRESETS[scheme_name], binding)
    placed = [p for leaf in result.leaves for p in (leaf.recto_page, leaf.verso_page) if p is not None]
    assert sorted(placed) == list(range(1, content_pages + 1))


@pytest.mark.parametrize("content_pages", [1, 5, 17, 64, 129])
def test_padding_is_less_than_one_sheet(content_pages):
    binding = load_binding_profile("pamphlet")
    scheme = PRESETS["folio"]
    result = plan(content_pages, scheme, binding)
    pages_per_sheet = scheme.leaves_per_sheet * (2 if scheme.duplex else 1)
    assert 0 <= result.padding_pages < pages_per_sheet


def test_signatures_respect_nest_max():
    binding = BindingProfile(nest_preferred=4, nest_max=6)
    result = plan(400, PRESETS["folio"], binding)
    for sig in range(1, result.signature_count + 1):
        assert 1 <= result.sheets_in_signature(sig) <= binding.nest_max


def test_hardcover_profile_adds_a_fully_blank_facing_leaf():
    binding = load_binding_profile("hardcover-casebound")
    result = plan(20, PRESETS["folio"], binding)
    blank_leaves = [leaf for leaf in result.leaves if leaf.recto_page is None and leaf.verso_page is None]
    assert blank_leaves  # leading_blank_leaves=1 must produce at least one
    placed = [p for leaf in result.leaves for p in (leaf.recto_page, leaf.verso_page) if p is not None]
    assert sorted(placed) == list(range(1, 21))


def test_single_leaf_scheme_is_plain_sequential_and_duplex_by_default():
    scheme = PRESETS["single-leaf"]
    assert scheme.duplex is True  # so each single unfolded leaf holds 2 pages (recto+verso)
    binding = BindingProfile(leading_blank_leaves=0, trailing_blank_leaves=0, nest_preferred=1, nest_max=1)
    result = plan(4, scheme, binding)
    assert result.signature_count == 2  # nest=1: every sheet/leaf is its own signature
    ordered = sorted(result.leaves, key=lambda leaf: leaf.signature_index)
    assert [(leaf.recto_page, leaf.verso_page) for leaf in ordered] == [(1, 2), (3, 4)]


def test_simplex_scheme_never_assigns_a_verso():
    result = plan(6, PRESETS["bag-fold"], load_binding_profile("pamphlet"))
    assert all(leaf.verso_page is None for leaf in result.leaves)
    placed = sorted(leaf.recto_page for leaf in result.leaves if leaf.recto_page is not None)
    assert placed == list(range(1, 7))


def test_folds_above_one_not_implemented():
    quarto = Scheme("quarto", folds=2, sheet_width_in=11, sheet_height_in=17)
    with pytest.raises(NotImplementedError):
        plan(50, quarto, load_binding_profile("pamphlet"))


def test_shipped_binding_profiles_load():
    for name in list_binding_profiles():
        profile = load_binding_profile(name)
        assert profile.name == name
        assert profile.nest_preferred >= 1
