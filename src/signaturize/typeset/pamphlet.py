#!/usr/bin/env python3
"""Wrap a pandoc-generated body.tex fragment with a title page, "THE END",
and a colophon page, sized to a trim size derived from a paper size +
fold scheme (see impose/scheme.py's resolve_scheme()).

Usage:
    python3 -m signaturize.typeset.pamphlet <story_dir> \\
        [--config <toml-or-profile>] [--paper <preset>] [--scheme <preset>]
Reads:  <story_dir>/meta.json, <story_dir>/body.tex
Writes: <story_dir>/booklet.tex
"""
import argparse
import datetime
import json
from string import Template
from pathlib import Path

from ..config import load_config
from ..impose.scheme import FOLD_PRESETS, PAPER_SIZES, resolve_scheme

TEMPLATE = Template(r"""\documentclass[12pt]{article}
\usepackage[paperwidth=${trim_width}in,paperheight=${trim_height}in,margin=${margin}in]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{$font}
\usepackage{graphicx}
\setkeys{Gin}{width=0.85\linewidth,keepaspectratio}
\linespread{1.15}
\pagestyle{empty}
\setlength{\parindent}{1.2em}
\begin{document}

% -- title page --------------------------------------------------------
\thispagestyle{empty}
\begin{center}
\vspace*{0.6in}
{\Huge\bfseries $title}\\[1.2em]
{\Large by $author}\\[1.8em]
$frontispiece
\vfill
{\normalsize $published_line}
\end{center}
\newpage

% -- story body ---------------------------------------------------------
$page_numbering_setup\input{body.tex}

% -- the end --------------------------------------------------------
\newpage
\thispagestyle{empty}
\vspace*{2in}
\begin{center}
{\Large\itshape THE END}
\end{center}
\newpage

% -- colophon --------------------------------------------------------
\thispagestyle{empty}
\vspace*{\fill}
\begin{center}
\small
$title\\
by $author\\[1em]
$published_line\\
This edition is in the public domain in the United States.\\
$source_line\\[1em]
Prepared as a keepsake pamphlet booklet, $prepared_line.
\end{center}
\vspace*{\fill}

\end{document}
""")


def cover_sequence(content_pages: int) -> list[int | None]:
    """Page sequence for the fixed document shape build() above produces:
    page 1 (the title page, recto of the signature's outermost leaf) is
    pinned first, with a forced blank on its verso -- the reverse of that
    same leaf -- standing in for a deliberately-skipped imprint page.
    Pages 2..content_pages follow in their natural order; padding to fill
    out a whole signature is left entirely to planner.plan()'s own
    general mechanism, exactly as it already handles any page count
    (verified against the original tool's own Peter Rabbit output, a
    29-page book -- not a multiple of 4 -- which pads correctly with no
    special-casing needed here; see tests/test_regression_legacy.py).

    This is a decision about *this* document's fixed shape -- not a
    general imposition concern -- so it lives here rather than in
    impose/planner.py, which stays content-agnostic and accepts this as
    an explicit `content_sequence` (see plan()'s own docstring).
    """
    if content_pages < 1:
        raise ValueError("content_pages must be >= 1")
    return [1, None] + list(range(2, content_pages + 1))


def latex_escape(s: str) -> str:
    return (
        s.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("#", r"\#")
    )


def build(
    story_dir: Path,
    trim_width_in: float,
    trim_height_in: float,
    margin_in: float,
    font_name: str,
    prepared_line: str | None,
    page_numbers: bool = False,
) -> None:
    """`page_numbers` turns on real, TeX-rendered page numbers (plain,
    centered, bottom of page) for the story body only -- the title page,
    "THE END", and colophon stay unnumbered (standard front-/back-matter
    convention), and numbering restarts at 1 for the first body page
    regardless of the title page ahead of it. This is a different thing
    from impose's own per-panel page-number overlay (impose/marks.py):
    that one is a verification aid impose draws itself and works on any
    typeset PDF; this one is real book content, specific to this fixed
    document shape, off by default so existing output doesn't change
    unless asked for."""
    meta = json.loads((story_dir / "meta.json").read_text(encoding="utf-8"))

    title = latex_escape(meta["title"])
    author = latex_escape(meta["author"])

    if meta.get("frontispiece"):
        frontispiece = f"\\includegraphics[width=0.65\\linewidth]{{{meta['frontispiece']}}}\\\\[1.2em]"
    else:
        frontispiece = ""

    published_line = f"First published {meta['year']}." if meta.get("year") else "First publication date unknown."

    if meta.get("gutenberg_id"):
        source_line = (
            f"Source: Project Gutenberg, ebook \\#{meta['gutenberg_id']} "
            f"(gutenberg.org/ebooks/{meta['gutenberg_id']})."
        )
    else:
        source_line = "Source: Project Gutenberg (gutenberg.org)."

    resolved_prepared_line = prepared_line or str(datetime.date.today().year)

    page_numbering_setup = "\\pagestyle{plain}\n\\setcounter{page}{1}\n" if page_numbers else ""

    tex = TEMPLATE.substitute(
        title=title,
        author=author,
        frontispiece=frontispiece,
        published_line=published_line,
        source_line=source_line,
        prepared_line=resolved_prepared_line,
        trim_width=trim_width_in,
        trim_height=trim_height_in,
        margin=margin_in,
        font=font_name,
        page_numbering_setup=page_numbering_setup,
    )
    (story_dir / "booklet.tex").write_text(tex, encoding="utf-8")
    print(f"Wrote {story_dir / 'booklet.tex'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story_dir", type=Path)
    ap.add_argument("--config", type=Path, help="TOML config file or shipped profile name (default: built-in defaults)")
    ap.add_argument("--paper", default="us-letter", choices=sorted(PAPER_SIZES), help="paper size preset (default: us-letter)")
    ap.add_argument("--scheme", default="folio", choices=sorted(FOLD_PRESETS), help="fold scheme preset (default: folio)")
    ap.add_argument("--prepared-line", default=None, help="default: current year")
    ap.add_argument("--page-numbers", action="store_true", help="number the story body pages (default: off)")
    args = ap.parse_args()
    config = load_config(args.config)
    scheme = resolve_scheme(PAPER_SIZES[args.paper], FOLD_PRESETS[args.scheme])
    build(
        args.story_dir, scheme.cell_width_in, scheme.cell_height_in, config.trim.margin_in, config.font.name,
        args.prepared_line, page_numbers=args.page_numbers,
    )


if __name__ == "__main__":
    main()
