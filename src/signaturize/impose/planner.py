"""Signature planner: turns a page count into a sequence of signatures,
each made of one or more physical sheets, following the fold's own nested
reading order and a binding profile's blank-leaf/padding choices.

Signatures are independent of any content structure (chapters, etc.) --
this module only knows page counts, blank leaves, and nest sizes. Content
pages are numbered 1..content_pages; leaves that get no content page are
blank (None).

folds=0 (single leaves): every sheet is its own leaf, filled in plain
sequential order -- no nesting, since there is no fold to nest within.

folds=1 (folio, nested signature): the classic saddle-stitch pattern --
within one signature of `n` sheets, sheet 1 is outermost and sheet n is
innermost. Reading front to back through the assembled signature you
encounter: sheet1's outward-facing leaf, sheet2's, ..., sheetn's (going
in), then sheetn's other leaf, ..., sheet1's other leaf (coming back out).
This is the same order impose/nested_folio.py's compute_layout() computes
for a single signature (see tests/test_planner.py for the equivalence
check) -- generalized here to (a) many signatures, filled from a shared
page sequence, and (b) blank leading/trailing/padding leaves as data
instead of two special-cased slots.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .binding import BindingProfile
from .scheme import Scheme


@dataclass(frozen=True)
class Leaf:
    """One physical leaf (a recto+verso pair, or just a recto for a
    simplex scheme) within one signature."""
    signature_index: int    # 1-indexed, order in the assembled book
    sheet_index: int        # 1-indexed, order within its signature (1 = outermost)
    sheet_slot: int         # 0-indexed raster position into scheme.sheet_panel_layout()'s grid
    recto_page: int | None  # 1-indexed source page number, or None for blank
    verso_page: int | None  # None for blank, or always None if the scheme is simplex


@dataclass(frozen=True)
class SignaturePlan:
    scheme: Scheme
    binding: BindingProfile
    leaves: tuple[Leaf, ...]
    content_pages: int
    padding_pages: int

    @property
    def signature_count(self) -> int:
        return max((leaf.signature_index for leaf in self.leaves), default=0)

    def sheets_in_signature(self, signature_index: int) -> int:
        return max(
            (leaf.sheet_index for leaf in self.leaves if leaf.signature_index == signature_index),
            default=0,
        )

    def leaves_of(self, signature_index: int, sheet_index: int) -> list[Leaf]:
        return [
            leaf for leaf in self.leaves
            if leaf.signature_index == signature_index and leaf.sheet_index == sheet_index
        ]

    def total_sheets(self) -> int:
        return sum(self.sheets_in_signature(s) for s in range(1, self.signature_count + 1))


def _group_sheets(total_sheets: int, binding: BindingProfile) -> list[int]:
    """Split `total_sheets` physical sheets into signatures of
    `binding.nest_preferred` sheets each, the last signature taking the
    remainder (merged into the previous one if that still fits
    nest_max, to avoid a lone tiny trailing signature)."""
    if total_sheets <= 0:
        return []
    pref = max(1, min(binding.nest_preferred, binding.nest_max))
    sizes = []
    remaining = total_sheets
    while remaining > 0:
        take = min(pref, remaining)
        sizes.append(take)
        remaining -= take
    if len(sizes) >= 2 and sizes[-1] < pref and sizes[-2] + sizes[-1] <= binding.nest_max:
        sizes[-2] += sizes[-1]
        sizes.pop()
    return sizes


def plan(content_pages: int, scheme: Scheme, binding: BindingProfile) -> SignaturePlan:
    """Build a SignaturePlan for a book of `content_pages` source pages."""
    if content_pages < 1:
        raise ValueError("content_pages must be >= 1")
    if scheme.folds not in (0, 1):
        raise NotImplementedError(
            f"planning for folds={scheme.folds} is not implemented yet "
            "(see scheme.py's module docstring)"
        )

    pages_per_leaf = 2 if scheme.duplex else 1
    leaves_per_sheet = scheme.leaves_per_sheet  # 1 for folds=0, 2 for folds=1

    content_leaves = math.ceil(content_pages / pages_per_leaf)
    total_leaves_needed = binding.leading_blank_leaves + content_leaves + binding.trailing_blank_leaves

    total_sheets = max(1, math.ceil(total_leaves_needed / leaves_per_sheet))
    sheet_sizes = _group_sheets(total_sheets, binding)

    total_leaves_planned = sum(sheet_sizes) * leaves_per_sheet
    # Padding pages fill out both (a) content_pages up to a whole leaf
    # (e.g. an odd page count leaves the last leaf's verso blank) and (b)
    # the leaves needed up to a whole number of sheets. Both land right
    # after the content, before any trailing blank leaves.
    padding_pages = (content_leaves * pages_per_leaf - content_pages) + (
        total_leaves_planned - total_leaves_needed
    ) * pages_per_leaf

    sequence: list[int | None] = (
        [None] * (binding.leading_blank_leaves * pages_per_leaf)
        + list(range(1, content_pages + 1))
        + [None] * padding_pages
        + [None] * (binding.trailing_blank_leaves * pages_per_leaf)
    )
    assert len(sequence) == total_leaves_planned * pages_per_leaf

    if scheme.folds == 0:
        leaves = _assign_flat(sequence, pages_per_leaf, sheet_sizes)
    else:
        leaves = _assign_nested_folio(sequence, pages_per_leaf, sheet_sizes)

    return SignaturePlan(scheme, binding, tuple(leaves), content_pages, padding_pages)


def _assign_flat(sequence, pages_per_leaf, sheet_sizes) -> list[Leaf]:
    leaves = []
    pos = 0
    for sig_index, n_sheets in enumerate(sheet_sizes, start=1):
        for sheet_index in range(1, n_sheets + 1):
            recto = sequence[pos]
            pos += 1
            verso = None
            if pages_per_leaf == 2:
                verso = sequence[pos]
                pos += 1
            leaves.append(Leaf(sig_index, sheet_index, 0, recto, verso))
    return leaves


def _assign_nested_folio(sequence, pages_per_leaf, sheet_sizes) -> list[Leaf]:
    leaves = []
    pos = 0
    for sig_index, n_sheets in enumerate(sheet_sizes, start=1):
        n_leaves = 2 * n_sheets
        for g in range(1, n_leaves + 1):
            recto = sequence[pos]
            pos += 1
            verso = None
            if pages_per_leaf == 2:
                verso = sequence[pos]
                pos += 1
            if g <= n_sheets:
                sheet_index, slot = g, 0          # inward pass: sheet's west leaf
            else:
                sheet_index, slot = 2 * n_sheets + 1 - g, 1  # outward pass: sheet's east leaf
            leaves.append(Leaf(sig_index, sheet_index, slot, recto, verso))
    return leaves
