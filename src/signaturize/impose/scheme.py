"""Physical sheet-folding schemes: how a printed sheet becomes one or more
leaves of a signature.

A Scheme describes ONE fold pattern for a single physical sheet: how many
times it is folded, whether both faces are printed (duplex) or only the
front (simplex), and the physical sheet size. sheet_panel_layout() is the
fold simulator: given `folds`, it returns, for every panel position on the
flat (unfolded, as-printed) sheet, which of this ONE sheet's own leaves
(recto/verso) lands there, and whether it must be printed rotated 180
degrees to read right-side-up once folded.

Only folds=0 (a single unfolded leaf) and folds=1 ("folio": one center
fold, as in the original pamphlet pipeline) are implemented here. folds=1
is checked byte-for-byte against the original pamphlet pipeline's own
nested-folio algorithm, preserved as golden values in
tests/golden/legacy_nested_folio_layout.json and checked against this
module's planner in tests/test_regression_legacy.py and
tests/test_planner.py. folds=2/3/4 (quarto/octavo/16mo) need a second,
perpendicular fold; working out the resulting panel rotation and
depth-nesting order from first principles, with no physical sheet at hand
to fold and check, is exactly the risk the project plan flags ("fold
conventions can only be validated on paper") -- a first attempt at
generalizing the fold simulator to two axes gave a *different* panel
layout than the validated folds=1 case for the one instance that could be
checked against the working legacy code, which means it cannot be trusted
without a physical reference. So sheet_panel_layout() raises
NotImplementedError for folds >= 2 rather than shipping unverified
geometry. planner.py and render.py are written generically against
`leaves_per_sheet` / `sheet_panel_layout()`, so adding quarto/octavo later
is a matter of extending this one function, not a redesign.

Paper size and fold shape are independent presets (PaperSize/PAPER_SIZES
and FoldScheme/FOLD_PRESETS below), combined by resolve_scheme() into the
one Scheme planner.py/render.py consume -- so e.g. "folio" fold shape and
"us-letter" paper size can be picked separately on any stage, with
orientation (portrait vs. landscape feed) decided by the fold, not the
paper. PRESETS is kept as a backward-compatible convenience: today's
named combinations, pre-resolved at us-letter.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Panel:
    """One panel position on a flat, as-printed sheet face.

    `rank` is this sheet's own local depth (0 = outermost of this sheet's
    own folding, i.e. the leaf closest to the sheet's outer surface;
    higher rank = closer to this sheet's own center fold).
    `side` is "recto" or "verso" of that depth-rank's leaf.
    `rotation` is 0 or 180 -- print the panel upside down if 180.
    """
    rank: int
    side: str  # "recto" | "verso"
    rotation: int  # 0 | 180


@dataclass(frozen=True)
class Scheme:
    """One named fold/sheet combination.

    `folds`: number of folds applied to each sheet (0=single leaf,
    1=folio; 2/3/4=quarto/octavo/16mo, not yet implemented -- see module
    docstring).
    `duplex`: both faces printed (True), or only the front (False, e.g. a
    simplex bag-fold pamphlet).
    `sheet_width_in`/`sheet_height_in`: the physical, as-fed sheet size.
    """
    name: str
    folds: int
    sheet_width_in: float
    sheet_height_in: float
    duplex: bool = True

    def __post_init__(self):
        if self.folds < 0:
            raise ValueError(f"folds must be >= 0, got {self.folds}")

    @property
    def leaves_per_sheet(self) -> int:
        return 2 ** self.folds

    @property
    def grid(self) -> tuple[int, int]:
        """(rows, cols) of panels per face. Folds alternate axis, columns
        first (matching the legacy single vertical fold)."""
        col_folds = -(-self.folds // 2)  # ceil(folds / 2)
        row_folds = self.folds // 2
        return (2 ** row_folds, 2 ** col_folds)

    @property
    def cell_width_in(self) -> float:
        _, cols = self.grid
        return self.sheet_width_in / cols

    @property
    def cell_height_in(self) -> float:
        rows, _ = self.grid
        return self.sheet_height_in / rows


def sheet_panel_layout(folds: int) -> tuple[list[list[Panel]], list[list[Panel]]]:
    """(front_grid, back_grid): grid[row][col] = Panel for that position on
    the flat, as-printed sheet. In traditional imposition terms, `front`
    is the sheet's "outer forme" (the printing pass whose pages end up
    facing outward once folded) and `back` is the "inner forme" (faces
    inward); `Panel.side` says whether a given leaf's recto or verso
    lands at that position. Validated for folds in {0, 1}; see module
    docstring for why folds >= 2 is not yet implemented."""
    if folds == 0:
        # A single unfolded leaf: front face is its recto, back its verso.
        front = [[Panel(rank=0, side="recto", rotation=0)]]
        back = [[Panel(rank=0, side="verso", rotation=0)]]
        return front, back
    if folds == 1:
        # One center fold: the sheet's FIRST-printed face ("front" --
        # outer forme) ends up facing outward once folded; the
        # SECOND-printed face ("back" -- inner forme) ends up facing
        # inward. West half's front = its recto, back = its verso; the
        # reverse for the east half. No rotation is needed for a single
        # fold.
        #
        # This is the reverse of what an earlier version of this module
        # assumed (front=inward, back=outward), based on reading the
        # original pre-signaturize pipeline's own sample output rather
        # than actually folding a physically-printed sheet -- that sample
        # was never itself fold-tested, and a real print+fold test showed
        # the title ending up on the *inside* under the old assumption.
        # Corrected here; see tests/test_regression_legacy.py and
        # tests/test_render.py for the physical-pass/content mapping this
        # now produces.
        front = [[Panel(0, "recto", 0), Panel(0, "verso", 0)]]
        back = [[Panel(0, "verso", 0), Panel(0, "recto", 0)]]
        return front, back
    raise NotImplementedError(
        f"folds={folds} (quarto/octavo/16mo) panel geometry is not yet "
        "implemented -- see this module's docstring. Use folds=0 (single "
        "leaves) or folds=1 (folio, nested multi-signature) for now."
    )


# nest (how many sheets are nested per signature) is a binding-profile
# decision, not part of either preset below -- see binding.py.


@dataclass(frozen=True)
class PaperSize:
    """A physical sheet's raw dimensions, stored portrait-natural
    (width_in <= height_in) regardless of how it will be fed -- the
    logical orientation a fold needs is FoldScheme.sheet_is_landscape
    (see resolve_scheme()); whether the *physical* PDF page is actually
    landscape-shaped or portrait-shaped-with-rotated-content is a
    separate, render-time choice -- see render.py's `landscape_feed`."""
    name: str
    width_in: float
    height_in: float


PAPER_SIZES: dict[str, PaperSize] = {
    "us-letter": PaperSize("us-letter", 8.5, 11.0),
    "a4": PaperSize("a4", 8.27, 11.69),
}
# More sizes (us-legal, tabloid/ledger, a3, ...) are a one-line dict entry
# each -- same shape as FOLD_PRESETS below.


@dataclass(frozen=True)
class FoldScheme:
    """One named fold pattern, independent of paper size.

    `sheet_is_landscape`: True if this fold needs a logically-wide sheet
    for its own panel math (e.g. a single vertical center fold needs a
    sheet wide enough for two side-by-side portrait leaves) -- see
    resolve_scheme(). This is purely about the fold's own geometry; it
    says nothing about whether the physical PDF page render() produces
    is actually landscape-shaped or portrait-shaped-with-rotated-content
    -- that's render()'s own `landscape_feed` option, a separate,
    printer-capability choice made at render time.
    """
    name: str
    folds: int
    duplex: bool = True
    sheet_is_landscape: bool = False

    def __post_init__(self):
        if self.folds < 0:
            raise ValueError(f"folds must be >= 0, got {self.folds}")


FOLD_PRESETS: dict[str, FoldScheme] = {
    "single-leaf": FoldScheme("single-leaf", folds=0),
    "folio": FoldScheme("folio", folds=1, sheet_is_landscape=True),
    "bag-fold": FoldScheme("bag-fold", folds=1, duplex=False, sheet_is_landscape=True),
}


def resolve_scheme(paper: PaperSize, fold: FoldScheme) -> Scheme:
    """Combine an independent paper size and fold scheme into the one
    Scheme planner.py/render.py consume, swapping paper's stored
    portrait-natural dimensions to logically-landscape iff the fold
    needs a wide sheet for its own panel math."""
    if fold.sheet_is_landscape:
        width_in, height_in = paper.height_in, paper.width_in
    else:
        width_in, height_in = paper.width_in, paper.height_in
    return Scheme(
        f"{fold.name} ({paper.name})", folds=fold.folds,
        sheet_width_in=width_in, sheet_height_in=height_in, duplex=fold.duplex,
    )


# Backward-compatible convenience: today's three named combinations,
# derived from FOLD_PRESETS at us-letter -- so existing PRESETS["folio"]
# -style call sites need no changes.
PRESETS: dict[str, Scheme] = {
    name: resolve_scheme(PAPER_SIZES["us-letter"], fold) for name, fold in FOLD_PRESETS.items()
}
