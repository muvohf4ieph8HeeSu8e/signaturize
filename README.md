# signaturize

Turns an epub into a print-ready saddle-stitch pamphlet booklet: extracts the
story text and images, typesets a trim-size PDF, then imposes that PDF onto
sheets ready for duplex printing, folding, and stapling.

Currently supports single-signature pamphlets (the whole booklet nests
inside one fold). Multi-signature (2-3 signature) booklets are planned but
not yet implemented.

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

## Usage

```
signaturize build <epub_path> --slug <slug> [--config config/default.toml] [--author "..."]
```

This writes intermediate files under `build/<slug>/`, PNG previews under
`preview/<slug>/`, and the final print-ready PDF plus a one-sheet test print
under `output/`.

Author is read from the epub's `dc:creator` metadata by default; pass
`--author` to override it if the epub doesn't set it.

### Configuration

`config/default.toml` holds the built-in defaults for paper size, trim
size, font, duplex-mirror compensation, and grayscale conversion. Copy it,
edit what you need, and pass `--config <path>` to any command.

## Tests

```
pytest
```
