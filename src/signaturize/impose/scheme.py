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
is checked byte-for-byte against the legacy impose/nested_folio.py
compute_layout() nested-folio algorithm in tests/test_regression_legacy.py
and tests/test_planner.py. folds=2/3/4 (quarto/octavo/16mo) need a second,
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
    the flat, as-printed sheet. Validated for folds in {0, 1}; see module
    docstring for why folds >= 2 is not yet implemented."""
    if folds == 0:
        # A single unfolded leaf: front face is its recto, back its verso.
        front = [[Panel(rank=0, side="recto", rotation=0)]]
        back = [[Panel(rank=0, side="verso", rotation=0)]]
        return front, back
    if folds == 1:
        # One center fold: the west half's front face ends up facing
        # inward once folded (verso of the west leaf), while its back
        # face ends up facing outward (recto) -- and the reverse for the
        # east half. This is the same A(front-west)/B(front-east)/
        # C(back-west)/D(back-east) relationship
        # impose/nested_folio.py has used since the original pamphlet
        # pipeline. No rotation is needed for a single fold.
        front = [[Panel(0, "verso", 0), Panel(0, "recto", 0)]]
        back = [[Panel(0, "recto", 0), Panel(0, "verso", 0)]]
        return front, back
    raise NotImplementedError(
        f"folds={folds} (quarto/octavo/16mo) panel geometry is not yet "
        "implemented -- see this module's docstring. Use folds=0 (single "
        "leaves) or folds=1 (folio, nested multi-signature) for now."
    )


# Named presets. nest (how many sheets are nested per signature) is a
# binding-profile decision, not part of the scheme -- see binding.py.
PRESETS: dict[str, Scheme] = {
    "single-leaf": Scheme("single-leaf", folds=0, sheet_width_in=8.5, sheet_height_in=11.0),
    "folio": Scheme("folio", folds=1, sheet_width_in=11.0, sheet_height_in=8.5),
    "bag-fold": Scheme("bag-fold", folds=1, sheet_width_in=11.0, sheet_height_in=8.5, duplex=False),
}
