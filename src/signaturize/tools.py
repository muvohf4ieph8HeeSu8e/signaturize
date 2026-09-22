"""External-tool helpers and the `signaturize doctor` dependency check."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def pdf_page_count(pdf_path: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True).stdout
    return int(out.split("Pages:")[1].split()[0])


@dataclass
class Check:
    name: str
    ok: bool
    needed_for: str
    required: bool = True
    detail: str = ""


def _executable(name: str, needed_for: str, required: bool = True) -> Check:
    path = shutil.which(name)
    return Check(name, path is not None, needed_for, required, path or "not found on PATH")


def _tex_file(filename: str, needed_for: str, required: bool = True) -> Check:
    if shutil.which("kpsewhich") is None:
        return Check(filename, False, needed_for, required, "kpsewhich not available")
    found = subprocess.run(["kpsewhich", filename], capture_output=True, text=True).stdout.strip()
    return Check(filename, bool(found), needed_for, required, found or "not found in TeX tree")


def _python_module(name: str, needed_for: str, required: bool = True) -> Check:
    found = importlib.util.find_spec(name) is not None
    return Check(name, found, needed_for, required, "importable" if found else "pip install " + name)


def run_checks() -> list[Check]:
    return [
        _executable("pdflatex", "typesetting (default engine) and the legacy pamphlet imposition"),
        _executable("pdfinfo", "page counting (poppler-utils)"),
        _executable("pdftoppm", "PNG previews (poppler-utils)"),
        _executable("pandoc", "html/markdown to LaTeX conversion"),
        _executable("convert", "grayscale image conversion (ImageMagick 6)", required=False),
        _executable("lualatex", "OpenType fonts via fontspec", required=False),
        _executable("xelatex", "OpenType fonts via fontspec (alternative to lualatex)", required=False),
        _executable("latexmk", "automatic multi-pass builds (own rerun loop is used if absent)", required=False),
        _executable("pdftotext", "test suite PDF assertions (poppler-utils)", required=False),
        _tex_file("tikz.sty", "legacy pamphlet imposition (tikz + calc)"),
        _tex_file("geometry.sty", "page size and margins"),
        _tex_file("bookman.sty", "default font (pamphlet profile)"),
        _tex_file("memoir.cls", "book typesetting class (planned)", required=False),
        _tex_file("microtype.sty", "microtypography (planned)", required=False),
        _tex_file("fontspec.sty", "OpenType fonts (planned)", required=False),
        _tex_file("tgpagella.sty", "TeX Gyre Pagella preset (planned)", required=False),
        _python_module("pikepdf", "PDF imposition (planned)", required=False),
        _python_module("PIL", "image processing (planned; package name Pillow)", required=False),
        _python_module("bs4", "epub ingestion (beautifulsoup4)"),
        _python_module("lxml", "epub ingestion"),
    ]


def doctor() -> int:
    """Print a dependency report. Returns 1 if a required item is missing."""
    checks = run_checks()
    width = max(len(c.name) for c in checks)
    missing_required = 0
    for c in checks:
        mark = "ok  " if c.ok else ("MISS" if c.required else "opt ")
        print(f"[{mark}] {c.name:<{width}}  {c.needed_for}" + ("" if c.ok else f"  ({c.detail})"))
        if c.required and not c.ok:
            missing_required += 1
    if missing_required:
        print(f"\n{missing_required} required item(s) missing.")
        return 1
    print("\nAll required items present.")
    return 0
