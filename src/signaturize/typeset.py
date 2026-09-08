#!/usr/bin/env python3
"""Wrap a pandoc-generated body.tex fragment with a title page, "THE END",
and a colophon page, sized to the configured trim size.

Usage:
    python3 -m signaturize.typeset <story_dir> [--config config/default.toml]
Reads:  <story_dir>/meta.json, <story_dir>/body.tex
Writes: <story_dir>/booklet.tex
"""
import argparse
import datetime
import json
from string import Template
from pathlib import Path

from .config import Config, load_config

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
\input{body.tex}

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


def latex_escape(s: str) -> str:
    return (
        s.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("#", r"\#")
    )


def build(story_dir: Path, config: Config, prepared_line: str | None) -> None:
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

    tex = TEMPLATE.substitute(
        title=title,
        author=author,
        frontispiece=frontispiece,
        published_line=published_line,
        source_line=source_line,
        prepared_line=resolved_prepared_line,
        trim_width=config.trim.width_in,
        trim_height=config.trim.height_in,
        margin=config.trim.margin_in,
        font=config.font.name,
    )
    (story_dir / "booklet.tex").write_text(tex, encoding="utf-8")
    print(f"Wrote {story_dir / 'booklet.tex'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story_dir", type=Path)
    ap.add_argument("--config", type=Path, help="path to a TOML config file (default: built-in defaults)")
    ap.add_argument("--prepared-line", default=None, help="default: current year")
    args = ap.parse_args()
    config = load_config(args.config)
    build(args.story_dir, config, args.prepared_line)


if __name__ == "__main__":
    main()
