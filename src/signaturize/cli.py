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
from .config import Config, ConfigError, load_config
from .impose import detect as detect_mod
from .impose import printguide
from .impose import render as render_mod
from .impose.binding import BindingError, list_binding_profiles, load_binding_profile
from .impose.planner import plan as plan_signatures
from .impose.scheme import FOLD_PRESETS, PAPER_SIZES, resolve_scheme
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


def typeset_story(
    story_dir: Path, config: Config, trim_width_in: float, trim_height_in: float, prepared_line: str | None,
    page_numbers: bool = False,
) -> Path:
    """Run the typeset stage on an already-ingested story (story_dir
    holding body.html + meta.json, from a prior ingest/extract() call):
    pandoc (HTML -> LaTeX body) + typeset.pamphlet's fixed template wrap +
    pdflatex. `trim_width_in`/`trim_height_in` normally come from a
    resolved Scheme's cell size (see impose.scheme.resolve_scheme()) so
    the result fits exactly into whatever paper+scheme will later impose
    it. `page_numbers` turns on real page numbers for the story body (see
    typeset.pamphlet.build()'s own docstring). Returns the resulting
    trim-size PDF (story_dir/trimmed.pdf). Shared by `build` and `typeset`
    so this sequence lives in one place."""
    run_pandoc(story_dir / "body.html", story_dir / "body.tex")
    typeset_mod.build(
        story_dir, trim_width_in, trim_height_in, config.trim.margin_in, config.font.name, prepared_line,
        page_numbers=page_numbers,
    )
    run_pdflatex(story_dir, "booklet.tex")
    trimmed_pdf = story_dir / "trimmed.pdf"
    shutil.copyfile(story_dir / "booklet.pdf", trimmed_pdf)
    return trimmed_pdf


def write_plan_artifacts(
    output_dir: Path, slug: str, title: str, signature_plan, imposed_pdf: Path,
) -> tuple[Path, Path]:
    """Write a <slug>-signature-plan.json (machine-readable leaf/sheet/
    signature plan) and a <slug>-PRINTING.md (human fold/gather guide,
    including a page map -- see printguide.py) for an imposed PDF, shared
    by both `build` and `impose`."""
    plan_json = output_dir / f"{slug}-signature-plan.json"
    plan_json.write_text(
        json.dumps(
            {
                "scheme": dataclasses.asdict(signature_plan.scheme),
                "binding": dataclasses.asdict(signature_plan.binding),
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
        printguide.render_printing_guide(title, signature_plan, imposed_pdf.name),
        encoding="utf-8",
    )
    print(f"  printing guide:   {printing_md}")
    return plan_json, printing_md


def ingest_command(
    epub_path: Path,
    slug: str,
    config_path: Path | None,
    build_dir: Path,
    author_override: str | None = None,
) -> None:
    """Run just the ingest stage: extract an epub into clean working text
    (build/<slug>/body.html + meta.json + images/), ready for `typeset`."""
    config = load_config(config_path)
    extract_mod.extract(epub_path, slug, build_dir, config.grayscale, author_override=author_override)


def typeset_command(
    slug: str,
    config_path: Path | None,
    build_dir: Path,
    output_dir: Path,
    preview_dir: Path | None,
    prepared_line: str | None,
    paper_name: str,
    scheme_name: str,
    page_numbers: bool = False,
) -> None:
    """Run just the typeset stage on an already-ingested story: pandoc +
    the fixed template wrap + pdflatex, producing a trim-size PDF sized
    to fit the chosen paper+scheme exactly. Mirrors `impose_pdf()` -- one
    stage, on the previous stage's own output."""
    if paper_name not in PAPER_SIZES:
        raise ConfigError(f"unknown paper size {paper_name!r}; available: {', '.join(sorted(PAPER_SIZES))}")
    if scheme_name not in FOLD_PRESETS:
        raise ConfigError(f"unknown scheme {scheme_name!r}; available: {', '.join(sorted(FOLD_PRESETS))}")
    scheme = resolve_scheme(PAPER_SIZES[paper_name], FOLD_PRESETS[scheme_name])

    config = load_config(config_path)
    story_dir = build_dir / slug
    if not (story_dir / "body.html").exists():
        raise ConfigError(f"{story_dir / 'body.html'} not found -- run `signaturize ingest` first")

    trimmed_pdf = typeset_story(
        story_dir, config, scheme.cell_width_in, scheme.cell_height_in, prepared_line, page_numbers=page_numbers,
    )
    pages = tools.pdf_page_count(trimmed_pdf)
    print(f"trimmed.pdf: {pages} pages")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = output_dir / f"{slug}-trimmed.pdf"
    shutil.copyfile(trimmed_pdf, out_pdf)
    print(f"  typeset PDF: {out_pdf}")

    if preview_dir is not None:
        render_previews(out_pdf, preview_dir / slug / "reading-order", "page")
        print(f"  previews:    {preview_dir / slug / 'reading-order'}")


def build_booklet(
    epub_path: Path,
    slug: str,
    config_path: Path | None,
    build_dir: Path,
    preview_dir: Path,
    output_dir: Path,
    paper_name: str,
    scheme_name: str,
    binding_name: str,
    pin_cover: bool,
    landscape_feed: bool = True,
    page_numbers: bool = False,
    prepared_line: str | None = None,
    author_override: str | None = None,
) -> None:
    """The original epub -> print-ready-booklet pipeline, now pure
    composition of the three independent stage commands below -- no
    ingest/typeset/imposition logic of its own. `output_dir/{slug}-trimmed.pdf`
    (written by typeset_command()) is typeset_command()'s own output and
    impose_pdf()'s own input; build just chains the three calls."""
    print("== ingest ==")
    ingest_command(epub_path, slug, config_path, build_dir, author_override=author_override)

    print("== typeset ==")
    typeset_command(
        slug, config_path, build_dir, output_dir, preview_dir, prepared_line, paper_name, scheme_name,
        page_numbers=page_numbers,
    )

    print("== impose ==")
    trimmed_pdf = output_dir / f"{slug}-trimmed.pdf"
    impose_pdf(
        trimmed_pdf, slug, paper_name, scheme_name, binding_name, output_dir, preview_dir,
        title=slug, test_sheet=True, marks=True, pin_cover=pin_cover, config_path=config_path,
        landscape_feed=landscape_feed,
    )


def _page_overlay_wanted(source_pdf: Path, mode: str) -> bool:
    """Whether to draw impose's own per-panel page-number label. `auto`
    skips it when the source PDF already prints page numbers, so the two
    don't print on top of each other."""
    if mode == "on":
        return True
    if mode == "off":
        return False
    if detect_mod.has_printed_page_numbers(source_pdf):
        print(
            "  source already prints page numbers: skipping the per-panel page-number overlay "
            "(collation marks kept; --page-overlay on to force it)"
        )
        return False
    return True


def impose_pdf(
    source_pdf: Path,
    slug: str,
    paper_name: str,
    scheme_name: str,
    binding_name: str,
    output_dir: Path,
    preview_dir: Path | None,
    title: str | None,
    test_sheet: bool,
    marks: bool,
    *,
    pin_cover: bool = False,
    config_path: Path | None = None,
    landscape_feed: bool = True,
    page_overlay: str = "auto",
) -> None:
    if paper_name not in PAPER_SIZES:
        raise ConfigError(f"unknown paper size {paper_name!r}; available: {', '.join(sorted(PAPER_SIZES))}")
    if scheme_name not in FOLD_PRESETS:
        raise ConfigError(f"unknown scheme {scheme_name!r}; available: {', '.join(sorted(FOLD_PRESETS))}")
    scheme = resolve_scheme(PAPER_SIZES[paper_name], FOLD_PRESETS[scheme_name])
    try:
        binding = load_binding_profile(binding_name)
    except BindingError as e:
        raise ConfigError(str(e)) from e

    config = load_config(config_path)
    n_pages = tools.pdf_page_count(source_pdf)
    content_sequence = typeset_mod.cover_sequence(n_pages) if pin_cover else None
    signature_plan = plan_signatures(n_pages, scheme, binding, content_sequence=content_sequence)
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

    overlay = marks and _page_overlay_wanted(source_pdf, page_overlay)

    output_dir.mkdir(parents=True, exist_ok=True)
    imposed_pdf = output_dir / f"{slug}-imposed.pdf"
    render_mod.render(
        source_pdf, signature_plan, imposed_pdf,
        marks=marks, page_overlay=overlay, duplex_mirror=config.imposition.duplex_mirror,
        landscape_feed=landscape_feed,
    )
    print(f"  imposed PDF:      {imposed_pdf}")

    write_plan_artifacts(output_dir, slug, title or slug, signature_plan, imposed_pdf)

    if test_sheet:
        test_sheet_pdf = output_dir / f"{slug}-test-sheet.pdf"
        render_mod.render(
            source_pdf, signature_plan, test_sheet_pdf,
            sheets_filter={(1, 1)}, marks=marks, page_overlay=overlay,
            duplex_mirror=config.imposition.duplex_mirror, landscape_feed=landscape_feed,
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
    build_p.add_argument("--paper", default="us-letter", choices=sorted(PAPER_SIZES), help="paper size preset (default: us-letter)")
    build_p.add_argument("--scheme", default="folio", choices=sorted(FOLD_PRESETS), help="fold scheme preset (default: folio)")
    build_p.add_argument(
        "--binding", default="pamphlet",
        help=f"binding profile name (default: pamphlet); available: {', '.join(list_binding_profiles())}",
    )
    build_p.add_argument(
        "--pin-cover", dest="pin_cover", action="store_true",
        help="pin the title page as this signature's cover, with a forced blank beside it (default: on)",
    )
    build_p.add_argument(
        "--no-pin-cover", dest="pin_cover", action="store_false",
        help="disable the pinned-cover content layout",
    )
    build_p.set_defaults(pin_cover=True)
    build_p.add_argument(
        "--landscape-feed", dest="landscape_feed", action="store_true",
        help="literal landscape PDF page for folio/bag-fold (the default; accepted for old commands)",
    )
    build_p.add_argument(
        "--portrait-feed", dest="landscape_feed", action="store_false",
        help="portrait PDF page with rotated content (/Rotate=90) for folio/bag-fold, for printers "
        "that cannot take a landscape page; displays sideways on screen",
    )
    build_p.set_defaults(landscape_feed=True)
    build_p.add_argument(
        "--page-numbers", action="store_true",
        help="number the story body pages in the trim PDF itself (TeX-rendered, default: off) -- a "
        "different thing from impose's own per-panel page-number overlay, see README",
    )
    build_p.add_argument("--prepared-line", default=None, help="colophon prepared-line text (default: current year)")
    build_p.add_argument("--build-dir", type=Path, default=Path("build"))
    build_p.add_argument("--preview-dir", type=Path, default=Path("preview"))
    build_p.add_argument("--output-dir", type=Path, default=Path("output"))

    sub.add_parser("doctor", help="check that required external tools and TeX packages are installed")

    ingest_p = sub.add_parser("ingest", help="extract an epub into clean working text (ingest stage)")
    ingest_p.add_argument("epub_path", type=Path)
    ingest_p.add_argument("--slug", required=True)
    ingest_p.add_argument("--config", type=Path, help="TOML config file or shipped profile name (default: built-in defaults)")
    ingest_p.add_argument("--author", help="override author (default: from epub dc:creator metadata)")
    ingest_p.add_argument("--build-dir", type=Path, default=Path("build"))

    typeset_p = sub.add_parser(
        "typeset",
        help="typeset an already-ingested story into a trim-size PDF (run `signaturize ingest` first)",
    )
    typeset_p.add_argument("slug")
    typeset_p.add_argument("--config", type=Path, help="TOML config file or shipped profile name (default: built-in defaults)")
    typeset_p.add_argument(
        "--paper", default="us-letter", choices=sorted(PAPER_SIZES),
        help="paper size preset (default: us-letter); combined with --scheme to derive the trim size",
    )
    typeset_p.add_argument(
        "--scheme", default="folio", choices=sorted(FOLD_PRESETS),
        help="fold scheme preset (default: folio); combined with --paper to derive the trim size",
    )
    typeset_p.add_argument(
        "--page-numbers", action="store_true",
        help="number the story body pages in the trim PDF itself (TeX-rendered, default: off) -- a "
        "different thing from impose's own per-panel page-number overlay, see README",
    )
    typeset_p.add_argument("--prepared-line", default=None, help="colophon prepared-line text (default: current year)")
    typeset_p.add_argument("--build-dir", type=Path, default=Path("build"))
    typeset_p.add_argument("--output-dir", type=Path, default=Path("output"))
    typeset_p.add_argument("--preview-dir", type=Path, default=None, help="if set, render PNG previews here")

    impose_p = sub.add_parser(
        "impose",
        help="impose any typeset PDF onto print-ready sheets (general planner: multi-signature, "
        "single leaves, hardcover blanks -- quarto/octavo not yet implemented, see impose/scheme.py)",
    )
    impose_p.add_argument("pdf_path", type=Path)
    impose_p.add_argument("--slug", required=True, help="used for output filenames")
    impose_p.add_argument("--paper", default="us-letter", choices=sorted(PAPER_SIZES), help="paper size preset (default: us-letter)")
    impose_p.add_argument("--scheme", default="folio", choices=sorted(FOLD_PRESETS), help="fold/sheet preset")
    impose_p.add_argument(
        "--binding", default="pamphlet",
        help=f"binding profile name (default: pamphlet); available: {', '.join(list_binding_profiles())}",
    )
    impose_p.add_argument(
        "--config", type=Path,
        help="TOML config file or shipped profile name; currently only [imposition] duplex_mirror affects impose",
    )
    impose_p.add_argument(
        "--pin-cover", dest="pin_cover", action="store_true",
        help="pin page 1 as this signature's cover, with a forced blank beside it "
        "(typeset.pamphlet's title-page convention; default: on, as in `build`)",
    )
    impose_p.add_argument(
        "--no-pin-cover", dest="pin_cover", action="store_false",
        help="disable the pinned-cover content layout (plain page order, for arbitrary PDFs)",
    )
    impose_p.set_defaults(pin_cover=True)
    impose_p.add_argument(
        "--landscape-feed", dest="landscape_feed", action="store_true",
        help="literal landscape PDF page for folio/bag-fold (the default; accepted for old commands)",
    )
    impose_p.add_argument(
        "--portrait-feed", dest="landscape_feed", action="store_false",
        help="portrait PDF page with rotated content (/Rotate=90) for folio/bag-fold, for printers "
        "that cannot take a landscape page; displays sideways on screen",
    )
    impose_p.set_defaults(landscape_feed=True)
    impose_p.add_argument("--title", help="book title, for PRINTING.md (default: --slug)")
    impose_p.add_argument("--output-dir", type=Path, default=Path("output"))
    impose_p.add_argument("--preview-dir", type=Path, default=None, help="if set, render PNG previews here")
    impose_p.add_argument(
        "--test-sheet", dest="test_sheet", action="store_true",
        help="also render just signature 1, sheet 1 (default: on)",
    )
    impose_p.add_argument(
        "--no-test-sheet", dest="test_sheet", action="store_false", help="skip the one-sheet test print",
    )
    impose_p.set_defaults(test_sheet=True)
    impose_p.add_argument(
        "--page-overlay", choices=["auto", "on", "off"], default="auto",
        help="impose's own per-panel page-number label: auto (default) skips it when the source PDF "
        "already prints page numbers, on always draws it, off never does; collation marks are unaffected",
    )
    impose_p.add_argument(
        "--no-marks", action="store_true",
        help="omit collation marks and impose's own per-panel page-number overlay (a verification aid, "
        "distinct from `typeset --page-numbers`, which is real TeX-rendered content)",
    )

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
                args.paper,
                args.scheme,
                args.binding,
                args.pin_cover,
                landscape_feed=args.landscape_feed,
                page_numbers=args.page_numbers,
                prepared_line=args.prepared_line,
                author_override=args.author,
            )
        elif args.command == "doctor":
            return tools.doctor()
        elif args.command == "ingest":
            ingest_command(
                args.epub_path,
                args.slug,
                args.config,
                args.build_dir,
                author_override=args.author,
            )
        elif args.command == "typeset":
            typeset_command(
                args.slug,
                args.config,
                args.build_dir,
                args.output_dir,
                args.preview_dir,
                args.prepared_line,
                args.paper,
                args.scheme,
                page_numbers=args.page_numbers,
            )
        elif args.command == "impose":
            impose_pdf(
                args.pdf_path,
                args.slug,
                args.paper,
                args.scheme,
                args.binding,
                args.output_dir,
                args.preview_dir,
                args.title,
                args.test_sheet,
                not args.no_marks,
                pin_cover=args.pin_cover,
                config_path=args.config,
                landscape_feed=args.landscape_feed,
                page_overlay=args.page_overlay,
            )
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
