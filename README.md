# signaturize

A toolsuite for turning source text (epub, Markdown, ...) into print-ready
signatures, in three stages: **ingest** (source -> clean working text,
`src/signaturize/ingest/`), **typeset** (working text -> a trim-size PDF,
`src/signaturize/typeset/`), and **impose** (trim-size PDF -> sheets ready
for folding, gathering, and binding, `src/signaturize/impose/`).

Two ways to use it today:

- `signaturize build <epub>` -- the original, still-working single-signature
  saddle-stitch pamphlet pipeline (extract -> pandoc -> typeset -> pdflatex
  -> impose), unchanged in behaviour since the beatrix-potter port.
- `signaturize impose <pdf>` -- a general imposition planner and renderer
  for **any** typeset PDF: multiple signatures, a binding profile's blank
  facing leaves and padding, staggered collation marks, and a generated
  print guide. See "General imposition" below for what's implemented.

The two are not yet wired together (`build`'s own imposition step still
uses the original single-signature code) -- connecting `build` (and a
future Markdown-based `typeset` stage) to the general `impose` planner is
follow-up work.

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

## Usage: the legacy pamphlet pipeline

```
signaturize build <epub_path> --slug <slug> [--config <toml-or-profile>] [--author "..."]
```

This writes intermediate files under `build/<slug>/`, PNG previews under
`preview/<slug>/`, and the final print-ready PDF plus a one-sheet test print
under `output/`.

Author is read from the epub's `dc:creator` metadata by default; pass
`--author` to override it if the epub doesn't set it.

## Usage: general imposition

```
signaturize impose <typeset_pdf> --slug <slug> \
    [--scheme single-leaf|folio|bag-fold] [--binding <profile>] \
    [--title "..."] [--output-dir output] [--preview-dir preview] \
    [--test-sheet] [--no-marks]
```

Takes any already-typeset PDF (trim size already set -- this command does
no typesetting) and writes, under `--output-dir`:

- `<slug>-imposed.pdf` -- the full print-ready, duplex-ready sheet sequence
- `<slug>-signature-plan.json` -- the computed plan (every leaf, its sheet,
  signature, and source pages) for inspection or tooling
- `<slug>-PRINTING.md` -- a generated print/fold/gather guide
- `<slug>-test-sheet.pdf` -- just signature 1, sheet 1, if `--test-sheet` is
  passed; print and fold this by hand before committing to a full run

**Schemes** (`--scheme`, see `src/signaturize/impose/scheme.py`):
`single-leaf` (no fold, loose leaves, duplex by default), `folio` (one
center fold, sheets nested into signatures -- the same physical layout the
legacy pamphlet pipeline uses, now generalized to multiple signatures),
`bag-fold` (a simplex folio). **Quarto, octavo, and 16mo (multi-fold
schemes) are not implemented yet** -- getting their panel rotation and
depth-nesting order right needs physical fold verification, which the
project doesn't have yet; `sheet_panel_layout()` raises `NotImplementedError`
rather than shipping unverified geometry. `folio` is checked byte-for-byte
against the legacy `compute_layout()` algorithm in
`tests/test_regression_legacy.py` and `tests/test_planner.py`.

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

Collation marks (a staggered bar on the spine per signature) and a slug
line (book/signature/sheet/face) are added by default; pass `--no-marks`
to omit them. The exact mark convention is documented, and reasonable, but
not tied to one specific bindery's house standard -- verify with a
physical `--test-sheet` before a real print run.

### Configuration

Built-in defaults (paper size, trim size, font, duplex-mirror compensation,
grayscale conversion) are shipped as the `pamphlet-folio-letter` profile in
`src/signaturize/config/profiles/`. Copy it, edit what you need, and pass
`--config <path>` (or a profile name) to any command. Unknown sections or
keys are an error, so typos are caught rather than silently ignored.

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
