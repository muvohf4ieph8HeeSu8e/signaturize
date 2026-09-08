#!/usr/bin/env python3
"""Impose a trim-size PDF onto landscape sheets for a side-fold pamphlet
booklet (single signature).

Physical format: a landscape sheet (config.paper), each holding two portrait
trim pages (config.trim) side by side, unrotated. Fold vertically down the
sheet's center; spine at the fold, standard small-book shape.

Slot naming (per sheet): front-left=A, front-right=B, back-left=C (directly
behind A), back-right=D (directly behind B).

Page flow, as a nested saddle-stitch signature (this is the order you
encounter physical sheet/slot pairs paging front-to-back through the
finished, stacked-and-folded booklet):

  sheet1-C (title, trim page 1)
  sheet1-A (forced blank -- stands in for an imprint/blank page, deliberately
            left blank rather than reproduced)
  sheet2-C, sheet2-A, sheet3-C, sheet3-A, ..., sheetS-C, sheetS-A   (inward)
  sheetS-B, sheetS-D, sheet(S-1)-B, sheet(S-1)-D, ..., sheet2-B, sheet2-D  (outward)
  sheet1-B, sheet1-D                                                (back to sheet 1)

Local read order per sheet mirrors: inward reads back-then-front (C,A);
outward reads front-then-back (B,D).

Trim pages 2..N (story + colophon) are threaded through that sequence in
order. Sheet count S is whatever makes 4S-2 (total slots minus the two
fixed cover slots) >= N-1.

Some printers mirror the back face of a duplexed sheet left/right relative
to the front face; config.imposition.duplex_mirror compensates for that by
swapping which of C/D lands west vs. east on the back side. It defaults to
off -- enable it only if your printer needs it.

Usage:
    python3 -m signaturize.impose <trimmed_pdf> --outfile <out.pdf> [--sheets 1]
"""
import argparse
import subprocess
from pathlib import Path

from .config import Config, load_config


def parse_sheets(spec: str, total_sheets: int):
    if spec is None:
        return list(range(1, total_sheets + 1))
    result = []
    for part in spec.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            result.extend(range(int(lo), int(hi) + 1))
        else:
            result.append(int(part))
    return result


def node(page: int | None, anchor: str, pdf_path: Path) -> str:
    if page is None:
        return ""
    return (
        f"\\node[anchor={anchor}, inner sep=0pt] at (current page.{anchor}) "
        f"{{\\includegraphics[page={page}]{{{pdf_path}}}}};"
    )


def label_node(text: str, corner: str) -> str:
    # corner: "north west" or "north east" -- small debug tag near the top
    # of each half, offset in from the true page edge.
    dx = "0.15in" if corner == "north west" else "-0.15in"
    return (
        f"\\node[anchor={corner}, inner sep=2pt, font=\\small, "
        f"fill=white, text=red] at ($(current page.{corner})+({dx},-0.15in)$) "
        f"{{{text}}};"
    )


def compute_layout(n_pages: int):
    """Returns {sheet_index: (A, B, C, D)}, 1-indexed sheets, None = blank."""
    remaining_needed = n_pages - 1  # trim pages 2..n_pages
    total_sheets = max(1, -(-(remaining_needed + 2) // 4))  # ceil((remaining_needed+2)/4)

    content = list(range(2, n_pages + 1))
    while len(content) < 4 * total_sheets - 2:
        content.append(None)

    layout = {i: [None, None, None, None] for i in range(1, total_sheets + 1)}
    layout[1][0] = None  # A: forced blank (stands in for the imprint page)
    layout[1][2] = 1     # C: title page

    idx = 0
    for k in range(2, total_sheets + 1):  # inward: back(C) then front(A)
        layout[k][2] = content[idx]; idx += 1
        layout[k][0] = content[idx]; idx += 1
    for k in range(total_sheets, 1, -1):  # outward: front(B) then back(D)
        layout[k][1] = content[idx]; idx += 1
        layout[k][3] = content[idx]; idx += 1
    layout[1][1] = content[idx]; idx += 1  # sheet1 B
    layout[1][3] = content[idx]; idx += 1  # sheet1 D

    return {i: tuple(v) for i, v in layout.items()}


def build(trimmed_pdf: Path, outfile: Path, sheets_spec, config: Config, labels: bool = False) -> None:
    n_pages = int(
        subprocess.run(["pdfinfo", str(trimmed_pdf)], capture_output=True, text=True, check=True)
        .stdout.split("Pages:")[1].split()[0]
    )
    layout = compute_layout(n_pages)
    total_sheets = len(layout)
    sheets = parse_sheets(sheets_spec, total_sheets)

    tex_parts = [
        f"""\\documentclass{{article}}
\\usepackage[paperwidth={config.paper.width_in}in,paperheight={config.paper.height_in}in,margin=0pt]{{geometry}}
\\usepackage{{graphicx}}
\\usepackage{{tikz}}
\\usetikzlibrary{{calc}}
\\pagestyle{{empty}}
\\setlength{{\\parindent}}{{0pt}}
\\begin{{document}}
"""
    ]
    for i in sheets:
        a, b, c, d = layout[i]
        # Front: as designed, west=A, east=B.
        # Back: config.imposition.duplex_mirror compensates for printers that
        # mirror the back face left/right relative to the front -- when on,
        # C (meant for behind-A) is placed at "east" and D (meant for
        # behind-B) is placed at "west" to compensate.
        if config.imposition.duplex_mirror:
            back_sides = (d, "D", c, "C")
        else:
            back_sides = (c, "C", d, "D")
        sides = [
            (a, "A", b, "B"),
            back_sides,
        ]
        for west_pg, west_label, east_pg, east_label in sides:
            tex_parts.append("\\begin{tikzpicture}[remember picture, overlay]\n")
            tex_parts.append(node(west_pg, "west", trimmed_pdf) + "\n")
            tex_parts.append(node(east_pg, "east", trimmed_pdf) + "\n")
            if labels:
                tex_parts.append(label_node(f"{west_label} (p{west_pg})" if west_pg else f"{west_label} (blank)", "north west") + "\n")
                tex_parts.append(label_node(f"{east_label} (p{east_pg})" if east_pg else f"{east_label} (blank)", "north east") + "\n")
            tex_parts.append("\\end{tikzpicture}\n\\newpage\n\n")
    tex_parts.append(r"\end{document}" + "\n")

    work_dir = outfile.parent
    tex_path = work_dir / "impose.tex"
    tex_path.write_text("".join(tex_parts), encoding="utf-8")

    # Two passes: TikZ's remember-picture/overlay mechanism needs a prior
    # .aux to resolve node placement -- a single cold pass silently drops
    # image content (LaTeX's own "Rerun to get cross-references right").
    for _ in range(2):
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "impose.tex"],
            cwd=work_dir, check=True, capture_output=True, text=True,
        )
    (work_dir / "impose.pdf").rename(outfile)

    print(f"Imposed {len(sheets)} sheet(s) ({n_pages} trim pages, {total_sheets} sheets total) -> {outfile}")
    for i in sheets:
        a, b, c, d = layout[i]
        print(f"  sheet {i}: front[A={a} B={b}]  back[C={c} D={d}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trimmed_pdf", type=Path)
    ap.add_argument("--outfile", type=Path, required=True)
    ap.add_argument("--sheets", help="e.g. '1' or '1-8' or '1,8' (default: all sheets)")
    ap.add_argument("--labels", action="store_true", help="print small A/B/C/D + page-number debug tags")
    ap.add_argument("--config", type=Path, help="path to a TOML config file (default: built-in defaults)")
    ap.add_argument("--duplex-mirror", action=argparse.BooleanOptionalAction, default=None,
                     help="override config's duplex-mirror setting")
    args = ap.parse_args()
    config = load_config(args.config)
    if args.duplex_mirror is not None:
        config.imposition.duplex_mirror = args.duplex_mirror
    build(args.trimmed_pdf.resolve(), args.outfile.resolve(), args.sheets, config, args.labels)


if __name__ == "__main__":
    main()
