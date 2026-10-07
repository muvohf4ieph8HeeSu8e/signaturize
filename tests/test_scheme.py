"""Unit tests for the paper-size / fold-scheme split in impose/scheme.py."""
from signaturize.impose.scheme import FOLD_PRESETS, PAPER_SIZES, PRESETS, resolve_scheme


def test_resolve_scheme_reproduces_legacy_presets_at_us_letter():
    us_letter = PAPER_SIZES["us-letter"]

    single_leaf = resolve_scheme(us_letter, FOLD_PRESETS["single-leaf"])
    assert (single_leaf.sheet_width_in, single_leaf.sheet_height_in, single_leaf.duplex) == (8.5, 11.0, True)

    folio = resolve_scheme(us_letter, FOLD_PRESETS["folio"])
    assert (folio.sheet_width_in, folio.sheet_height_in, folio.duplex) == (11.0, 8.5, True)

    bag_fold = resolve_scheme(us_letter, FOLD_PRESETS["bag-fold"])
    assert (bag_fold.sheet_width_in, bag_fold.sheet_height_in, bag_fold.duplex) == (11.0, 8.5, False)


def test_presets_dict_matches_resolve_scheme_at_us_letter():
    us_letter = PAPER_SIZES["us-letter"]
    for name, fold in FOLD_PRESETS.items():
        resolved = resolve_scheme(us_letter, fold)
        assert PRESETS[name].sheet_width_in == resolved.sheet_width_in
        assert PRESETS[name].sheet_height_in == resolved.sheet_height_in
        assert PRESETS[name].duplex == resolved.duplex
        assert PRESETS[name].folds == resolved.folds


def test_sheet_is_landscape_swaps_paper_dimensions():
    a4 = PAPER_SIZES["a4"]
    assert a4.width_in < a4.height_in  # stored portrait-natural

    portrait_scheme = resolve_scheme(a4, FOLD_PRESETS["single-leaf"])  # sheet_is_landscape=False
    assert (portrait_scheme.sheet_width_in, portrait_scheme.sheet_height_in) == (a4.width_in, a4.height_in)

    landscape_scheme = resolve_scheme(a4, FOLD_PRESETS["folio"])  # sheet_is_landscape=True
    assert (landscape_scheme.sheet_width_in, landscape_scheme.sheet_height_in) == (a4.height_in, a4.width_in)
