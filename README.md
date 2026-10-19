# signaturize

A toolsuite for turning source text (epub, Markdown, ...) into print-ready
signatures, in three stages: **ingest** (source -> clean working text,
`src/signaturize/ingest/`), **typeset** (working text -> a trim-size PDF,
`src/signaturize/typeset/`), and **impose** (trim-size PDF -> sheets ready
for folding, gathering, and binding, `src/signaturize/impose/`).

Run it as one command, or as its three independent stages:

- `signaturize build <epub>` -- the original saddle-stitch pamphlet
  pipeline, start to finish (ingest -> pandoc -> typeset -> pdflatex ->
  impose). `build` is pure composition of the three stage commands below
  -- it has no ingest/typeset/imposition logic of its own, just chains
  their own calls and passes `--paper`/`--scheme`/`--binding`/
  `--pin-cover`/`--portrait-feed`/`--page-numbers` through to whichever
  of them needs it.
- `signaturize ingest <epub>` -- just the ingest stage: extract one tale
  into clean working text (HTML body + metadata + images), ready for
  `typeset`.
- `signaturize typeset <slug>` -- just the typeset stage: wrap an
  already-ingested story in its fixed title/body/colophon template and
  typeset it to a trim-size PDF sized to fit a chosen paper size + fold
  scheme exactly, ready for `impose`. `--page-numbers` adds real,
  TeX-rendered page numbers to the story body.
- `signaturize impose <pdf>` -- just the impose stage: the general
  imposition planner and renderer, for **any** typeset PDF: multiple
  signatures, a binding profile's blank facing leaves and padding, small
  per-panel page numbers, staggered collation marks, a generated print
  guide, and (with `--pin-cover`) the same title-page-as-cover content
  layout `build` uses by default. See "General imposition" below for
  what's implemented.

`typeset` and `impose` both take `--paper` (physical sheet size) and
`--scheme` (fold pattern) as independent presets, combined at use time --
see "Paper sizes" and "Schemes" below. `build` and the three standalone
stage commands all share one implementation
(`src/signaturize/cli.py`'s stage functions and
`src/signaturize/impose/{planner,render,scheme}.py`). The remaining
follow-up work is a Markdown-based (non-epub) source for the `typeset`
stage, and quarto/octavo/16mo fold schemes (see "Schemes" below).

## System dependencies

Install these separately; they're invoked as external commands:

- **ImageMagick** (`convert`) -- grayscale image conversion
- **pandoc** -- HTML to LaTeX conversion
- **TeX Live** (or another LaTeX distribution) with `pdflatex` and the
  `tikz` (+`calc` library), `geometry`, `graphicx`, `fontenc`, `inputenc`,
  and `bookman` packages
- **poppler-utils** (`pdfinfo`, `pdftoppm`) -- page counting and PNG preview
  rendering

On Debian/Ubuntu:

```
sudo apt install imagemagick pandoc texlive-latex-extra texlive-fonts-extra poppler-utils
```

## Install

```
pip install -e .
```

(pulls in `pikepdf`, used by the general `impose` command.)

## Usage: the whole pamphlet pipeline

```
signaturize build <epub_path> --slug <slug> \
    [--config <toml-or-profile>] [--author "..."] \
    [--paper us-letter|a4] [--scheme single-leaf|folio|bag-fold] \
    [--binding <profile>] [--pin-cover | --no-pin-cover] [--portrait-feed] \
    [--page-numbers] [--prepared-line "..."]
```

This writes intermediate files under `build/<slug>/`, PNG previews under
`preview/<slug>/`, and under `output/`: the trim-size PDF
(`<slug>-trimmed.pdf`), the print-ready imposed PDF (`<slug>-imposed.pdf`),
a one-sheet test print (`<slug>-test-sheet.pdf`), and the
`<slug>-signature-plan.json`/`<slug>-PRINTING.md` the `impose` stage below
also produces on its own. Defaults (`us-letter`/`folio`/`pamphlet`/cover
pinned on) reproduce the original pipeline's exact physical layout.

Author is read from the epub's `dc:creator` metadata by default; pass
`--author` to override it if the epub doesn't set it.

## Usage: running the stages independently

```
signaturize ingest <epub_path> --slug <slug> [--config <toml-or-profile>] [--author "..."]
```

Extracts one tale into `build/<slug>/` (`body.html`, `meta.json`,
`images/`), ready for `typeset`. Same `--author` behavior as `build`.

```
signaturize typeset <slug> \
    [--config <toml-or-profile>] [--prepared-line "..."] \
    [--paper us-letter|a4] [--scheme single-leaf|folio|bag-fold] \
    [--page-numbers] \
    [--build-dir build] [--output-dir output] [--preview-dir preview]
```

Reads `build/<slug>/body.html` + `meta.json` (from a prior `ingest` run --
or a prior `build` run, since `build` writes the same files on its way
through) and writes `<slug>-trimmed.pdf` under `--output-dir`, sized to
the chosen `--paper` + `--scheme`'s per-leaf cell exactly, ready for
`impose`. Errors out with a clear message if `ingest` hasn't been run yet
for that slug.

`--page-numbers` adds real, TeX-rendered page numbers (plain, centered,
bottom of page) to the story body only -- the title page, "THE END", and
colophon stay unnumbered, and numbering restarts at 1 for the first body
page. Off by default. This is unrelated to `impose`'s own per-panel
page-number overlay below (a verification aid it draws itself, working
on any typeset PDF, not just this project's own). When both would apply,
`impose` notices the real numbers and leaves the overlay off by default.

Then impose it, same as any other typeset PDF -- see below.

## Usage: general imposition

```
signaturize impose <typeset_pdf> --slug <slug> \
    [--paper us-letter|a4] [--scheme single-leaf|folio|bag-fold] \
    [--binding <profile>] [--config <toml-or-profile>] [--pin-cover | --no-pin-cover] \
    [--portrait-feed] \
    [--title "..."] [--output-dir output] [--preview-dir preview] \
    [--test-sheet | --no-test-sheet] [--no-marks]
```

Takes any already-typeset PDF (trim size already set to fit the chosen
`--paper`/`--scheme` -- this command does no typesetting) and writes,
under `--output-dir`:

- `<slug>-imposed.pdf` -- the full print-ready, duplex-ready sheet sequence
- `<slug>-signature-plan.json` -- the computed plan (every leaf, its sheet,
  signature, and source pages) for inspection or tooling
- `<slug>-PRINTING.md` -- a generated print/fold/gather guide, including a
  page map (which trim page lands on which physical half of each sheet,
  before folding) so you can check page order without opening the imposed
  PDF and flipping between a sheet's front and back pages
- `<slug>-test-sheet.pdf` -- just signature 1, sheet 1, unless
  `--no-test-sheet` is passed; print and fold this by hand before committing to a full run

**Paper sizes** (`--paper`, see `PAPER_SIZES` in
`src/signaturize/impose/scheme.py`): `us-letter` (8.5in x 11in, the
default), `a4` (8.27in x 11.69in, i.e. 210mm x 297mm). Stored portrait-natural; more
sizes are a one-line dict entry each.

**Schemes** (`--scheme`, see `FOLD_PRESETS` in
`src/signaturize/impose/scheme.py`): `single-leaf` (no fold, loose
leaves, duplex by default -- a single sheet printed and bound as-is, no
folding at all), `folio` (one center fold, sheets nested into
signatures), `bag-fold` (a simplex folio). Each fold needs a particular
*logical* sheet shape for its own panel math (`folio`/`bag-fold` need a
logically-wide sheet, room for two side-by-side portrait leaves;
`single-leaf` keeps the paper's natural portrait shape) -- combined with
`--paper` via `resolve_scheme()` into the sheet dimensions used for that
math. **Quarto, octavo, and 16mo (multi-fold schemes) are not
implemented yet** -- getting their panel rotation and depth-nesting
order right needs physical fold verification, which the project doesn't
have yet; `sheet_panel_layout()` raises `NotImplementedError` rather than
shipping unverified geometry. `folio` is checked byte-for-byte against
the original pamphlet pipeline's own nested-folio algorithm, pinned to
golden values in `tests/golden/legacy_nested_folio_layout.json` and
checked in `tests/test_regression_legacy.py` and `tests/test_planner.py`.

By default, a scheme that needs a logically-wide sheet (`folio`,
`bag-fold`) produces a literal landscape PDF page, which displays upright
on screen. This is the path checked against five physically printed and
folded books. Pass `--portrait-feed` if your printer cannot take a
landscape page: the page is then built the same way and flagged with the
PDF's standard `/Rotate` attribute so it prints rotated into the paper's
natural portrait shape. That encoding is necessarily sideways in a flat,
straight-on preview (on screen, or a print preview), and it is a reasoned
default rather than something physically confirmed. `--landscape-feed` is
still accepted and does nothing now (it used to opt into the landscape
page). Either way, verify with a physical `--test-sheet` (and the page
numbers below) before committing to a full run, as with `duplex_mirror`
below and the unimplemented multi-fold schemes above.

**Binding profiles** (`--binding`, see
`src/signaturize/impose/binding_profiles/*.toml`): `pamphlet` (staple, no
facing blanks, large nested signatures), `sewn-softcover` (smaller
signatures), `hardcover-casebound` (blank leaf front and back for the
case), `perfect-bound-leaves` (loose single leaves, no nesting). Pass a
shipped profile's bare name; to customize one, copy its TOML from
`impose/binding_profiles/` into your own project (support for `--binding
<path>` to an arbitrary file, matching how `--config` works, is a small
follow-up). Padding beyond a profile's `max_pad_pages` prints a warning,
not an error.

**`--pin-cover`**: pins the typeset PDF's page 1 as the front cover (the
recto of the signature's outermost leaf), with a forced blank on that
leaf's verso -- standing in for a deliberately-skipped imprint page.
Padding needed to reach a whole number of sheets is handled entirely by
the general planner, the same way it already does for any page count
(this works for source material that doesn't divide evenly into whole
sheets -- e.g. a 29-page book -- with no special-casing beyond the cover
pin itself). This is the content-layer convention
`typeset.pamphlet.build()`'s fixed title-page template is designed
around, and on by default for both `build` and `impose` (`--no-pin-cover`
to disable -- do so for an arbitrary PDF whose page 1 isn't a cover).

A small page number labels every panel by default (its trim page
number, bottom-center of its cell) so you can verify order after
printing and folding without reading the actual content, and a
collation mark (a staggered bar on the spine) is added once per
signature, on its outermost sheet's outward-facing side -- not once per
sheet, since its purpose (checking a gathered stack of signatures
without unfolding any of them) only makes sense once per signature.
If the source PDF already prints its own page numbers (a numbered
footer or header that steps up page by page), `impose` detects that and
skips the page-number label so the two don't stack; the collation marks
are kept. Control it with `--page-overlay auto|on|off` (default `auto`).
Pass `--no-marks` to omit both. The exact mark convention is documented,
and reasonable, but not tied to one specific bindery's house standard --
verify with a
physical `--test-sheet` before a real print run.

### Configuration

Built-in defaults (text margin, font, duplex-mirror compensation,
grayscale conversion) are shipped as the `default` profile in
`src/signaturize/config/profiles/`. Copy it, edit what you need, and pass
`--config <path>` (or a profile name) to any command. Unknown sections or
keys are an error, so typos are caught rather than silently ignored.
Paper and trim size are *not* configured here -- they're chosen via
`--paper`/`--scheme` on `typeset`/`impose`/`build` (see above).

### Checking your setup

```
signaturize doctor
```

Lists which external tools, TeX packages and Python modules are present,
and which are needed for what.

## Tests

```
pytest
```
