#!/usr/bin/env python3
"""End-to-end orchestrator: extract -> pandoc -> typeset -> pdflatex -> impose
-> render previews.

Usage:
    signaturize build <epub_path> --slug <slug> [--config <toml-or-profile>]
        [--build-dir build] [--preview-dir preview] [--output-dir output]
"""
import argparse
import dataclasses
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import tools
from .config import ConfigError, load_config
from .impose import nested_folio as impose_mod
from .impose import printguide
from .impose import render as render_mod
from .impose.binding import BindingError, list_binding_profiles, load_binding_profile
from .impose.planner import plan as plan_signatures
from .impose.scheme import PRESETS
from .ingest import epub as extract_mod
from .typeset import pamphlet as typeset_mod


def run_pandoc(body_html: Path, body_tex: Path) -> None:
    subprocess.run(
        ["pandoc", str(body_html), "-f", "html", "-t", "latex-smart", "--wrap=preserve", "-o", str(body_tex)],
        check=True,
    )


def run_pdflatex(story_dir: Path, tex_name: str) -> None:
    log_path = story_dir / "pdflatex.log"
    with log_path.open("w", encoding="utf-8") as log_file:
        try:
            subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_name],
                cwd=story_dir, check=True, stdout=log_file, stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError:
            tail = log_path.read_text(encoding="utf-8").splitlines()[-40:]
            print(f"pdflatex failed, see {log_path}", file=sys.stderr)
            print("\n".join(tail), file=sys.stderr)
            raise


def render_previews(pdf_path: Path, out_dir: Path, prefix: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdftoppm", "-png", "-r", "100", str(pdf_path), str(out_dir / prefix)], check=True)


def build_booklet(
    epub_path: Path,
    slug: str,
    config_path: Path | None,
    build_dir: Path,
    preview_dir: Path,
    output_dir: Path,
    author_override: str | None = None,
) -> None:
    config = load_config(config_path)
    story_dir = build_dir / slug

    print("== extract ==")
    extract_mod.extract(epub_path, slug, build_dir, config.grayscale, author_override=author_override)

    print("== html -> latex body ==")
    run_pandoc(story_dir / "body.html", story_dir / "body.tex")

    print("== build wrapper .tex ==")
    typeset_mod.build(story_dir, config, prepared_line=None)

    print("== typeset trim-size pdf ==")
    run_pdflatex(story_dir, "booklet.tex")
    trimmed_pdf = story_dir / "trimmed.pdf"
    shutil.copyfile(story_dir / "booklet.pdf", trimmed_pdf)

    pages = tools.pdf_page_count(trimmed_pdf)
    print(f"trimmed.pdf: {pages} pages")

    print("== impose for printing (side-by-side, landscape sheet, cover special-cased) ==")
    output_dir.mkdir(parents=True, exist_ok=True)
    # impose_mod.build() changes cwd to the output dir for pdflatex, so
    # trimmed_pdf must be absolute or its relative path breaks.
    trimmed_pdf_abs = trimmed_pdf.resolve()
    booklet_out = output_dir / f"{slug}-booklet.pdf"
    impose_mod.build(trimmed_pdf_abs, booklet_out.resolve(), None, config)

    print("== one-sheet physical test (sheet 1 only) ==")
    test_sheet_out = output_dir / f"{slug}-test-sheet.pdf"
    impose_mod.build(trimmed_pdf_abs, test_sheet_out.resolve(), "1", config)

    print("== render previews ==")
    render_previews(trimmed_pdf, preview_dir / slug / "reading-order", "page")
    render_previews(booklet_out, preview_dir / slug / "sheet-order", "sheet")

    print("Done.")
    print(f"  trim PDF:     {trimmed_pdf} ({pages} pages)")
    print(f"  print-ready:  {booklet_out}")
    print(f"  test sheet:   {test_sheet_out}")
    print(f"  previews:     {preview_dir / slug}")


def impose_pdf(
    source_pdf: Path,
    slug: str,
    scheme_name: str,
    binding_name: str,
    output_dir: Path,
    preview_dir: Path | None,
    title: str | None,
    test_sheet: bool,
    marks: bool,
) -> None:
    if scheme_name not in PRESETS:
        raise ConfigError(f"unknown scheme {scheme_name!r}; available: {', '.join(sorted(PRESETS))}")
    scheme = PRESETS[scheme_name]
    try:
        binding = load_binding_profile(binding_name)
    except BindingError as e:
        raise ConfigError(str(e)) from e

    n_pages = tools.pdf_page_count(source_pdf)
    signature_plan = plan_signatures(n_pages, scheme, binding)
    print(
        f"{n_pages} source page(s) -> {signature_plan.signature_count} signature(s), "
        f"{signature_plan.total_sheets()} sheet(s), {signature_plan.padding_pages} padding page(s)"
    )
    if signature_plan.padding_pages > binding.max_pad_pages:
        print(
            f"  warning: padding ({signature_plan.padding_pages} pages) exceeds this binding "
            f"profile's max_pad_pages ({binding.max_pad_pages})",
            file=sys.stderr,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    imposed_pdf = output_dir / f"{slug}-imposed.pdf"
    render_mod.render(source_pdf, signature_plan, imposed_pdf, marks=marks, slug_prefix=f"{slug} ")
    print(f"  imposed PDF:      {imposed_pdf}")

    plan_json = output_dir / f"{slug}-signature-plan.json"
    plan_json.write_text(
        json.dumps(
            {
                "scheme": dataclasses.asdict(scheme),
                "binding": dataclasses.asdict(binding),
                "content_pages": signature_plan.content_pages,
                "padding_pages": signature_plan.padding_pages,
                "signature_count": signature_plan.signature_count,
                "leaves": [dataclasses.asdict(leaf) for leaf in signature_plan.leaves],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  signature plan:   {plan_json}")

    printing_md = output_dir / f"{slug}-PRINTING.md"
    printing_md.write_text(
        printguide.render_printing_guide(title or slug, signature_plan, imposed_pdf.name), encoding="utf-8"
    )
    print(f"  printing guide:   {printing_md}")

    if test_sheet:
        test_sheet_pdf = output_dir / f"{slug}-test-sheet.pdf"
        render_mod.render(
            source_pdf, signature_plan, test_sheet_pdf,
            sheets_filter={(1, 1)}, marks=marks, slug_prefix=f"{slug} ",
        )
        print(f"  test sheet:       {test_sheet_pdf}")

    if preview_dir is not None:
        render_previews(imposed_pdf, preview_dir / slug / "sheet-order", "sheet")
        print(f"  previews:         {preview_dir / slug / 'sheet-order'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="signaturize")
    sub = ap.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build", help="build a print-ready booklet PDF from an epub")
    build_p.add_argument("epub_path", type=Path)
    build_p.add_argument("--slug", required=True)
    build_p.add_argument("--config", type=Path, help="TOML config file or shipped profile name (default: built-in defaults)")
    build_p.add_argument("--author", help="override author (default: from epub dc:creator metadata)")
    build_p.add_argument("--build-dir", type=Path, default=Path("build"))
    build_p.add_argument("--preview-dir", type=Path, default=Path("preview"))
    build_p.add_argument("--output-dir", type=Path, default=Path("output"))

    sub.add_parser("doctor", help="check that required external tools and TeX packages are installed")

    impose_p = sub.add_parser(
        "impose",
        help="impose any typeset PDF onto print-ready sheets (general planner: multi-signature, "
        "single leaves, hardcover blanks -- quarto/octavo not yet implemented, see impose/scheme.py)",
    )
    impose_p.add_argument("pdf_path", type=Path)
    impose_p.add_argument("--slug", required=True, help="used for output filenames")
    impose_p.add_argument("--scheme", default="folio", choices=sorted(PRESETS), help="fold/sheet preset")
    impose_p.add_argument(
        "--binding", default="pamphlet",
        help=f"binding profile name (default: pamphlet); available: {', '.join(list_binding_profiles())}",
    )
    impose_p.add_argument("--title", help="book title, for PRINTING.md (default: --slug)")
    impose_p.add_argument("--output-dir", type=Path, default=Path("output"))
    impose_p.add_argument("--preview-dir", type=Path, default=None, help="if set, render PNG previews here")
    impose_p.add_argument("--test-sheet", action="store_true", help="also render just signature 1, sheet 1")
    impose_p.add_argument("--no-marks", action="store_true", help="omit collation marks and slug lines")

    args = ap.parse_args(argv)
    try:
        if args.command == "build":
            build_booklet(
                args.epub_path,
                args.slug,
                args.config,
                args.build_dir,
                args.preview_dir,
                args.output_dir,
                author_override=args.author,
            )
        elif args.command == "doctor":
            return tools.doctor()
        elif args.command == "impose":
            impose_pdf(
                args.pdf_path,
                args.slug,
                args.scheme,
                args.binding,
                args.output_dir,
                args.preview_dir,
                args.title,
                args.test_sheet,
                not args.no_marks,
            )
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
