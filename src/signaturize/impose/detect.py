"""Detect whether an already-typeset PDF carries its own printed page
numbers, so `impose` doesn't stack its per-panel verification label on top
of them (see marks.add_page_number()).

Heuristic, via `pdftotext -bbox`: on each page, look for a bare integer word
sitting in the bottom (or, failing that, top) strip of the page. The PDF
counts as numbered when most text-bearing pages have such a word AND those
words step up by one from page to page. The sequence test is what keeps a
stray number in a margin, or a chapter heading near the page edge, from
being mistaken for a folio. Numbering that starts partway in (front matter
unnumbered) or restarts (a part divider) still passes, since only adjacent
pairs are compared.
"""
from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path

EDGE_STRIP_FRACTION = 0.12  # bottom/top 12% of the page height
MIN_NUMBERED_FRACTION = 0.5  # of text-bearing pages
MIN_CONSECUTIVE_FRACTION = 0.8  # of adjacent numbered pairs
MIN_PAIRS = 2

_PAGE_RE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)
_WORD_RE = re.compile(
    r'<word xMin="[\d.]+" yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)">(.*?)</word>', re.S
)


def _page_number_candidate(height: float, body: str) -> int | None:
    """The folio-like integer on one page, or None. Bottom strip is
    preferred over the top strip; within a strip, the word nearest the edge."""
    bottom: list[tuple[float, int]] = []
    top: list[tuple[float, int]] = []
    for y_min, y_max, text in _WORD_RE.findall(body):
        word = html.unescape(text).strip()
        if not word.isdigit() or len(word) > 4:
            continue
        y_min_f, y_max_f = float(y_min), float(y_max)
        if y_max_f >= height * (1 - EDGE_STRIP_FRACTION):
            bottom.append((height - y_max_f, int(word)))
        elif y_min_f <= height * EDGE_STRIP_FRACTION:
            top.append((y_min_f, int(word)))
    for group in (bottom, top):
        if group:
            return min(group)[1]
    return None


def has_printed_page_numbers(pdf_path: Path) -> bool:
    """True if `pdf_path` looks like it already prints its own page
    numbers (see module docstring). False when poppler's `pdftotext` is
    unavailable or fails, so the overlay is kept by default."""
    try:
        xml = subprocess.run(
            ["pdftotext", "-bbox", str(pdf_path), "-"], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return False

    candidates: list[int | None] = []
    for _w, height, body in _PAGE_RE.findall(xml):
        if not _WORD_RE.search(body):
            continue  # blank page: neither numbered nor un-numbered
        candidates.append(_page_number_candidate(float(height), body))

    if not candidates:
        return False
    found = [(i, n) for i, n in enumerate(candidates) if n is not None]
    if len(found) / len(candidates) < MIN_NUMBERED_FRACTION:
        return False
    pairs = [(a, b) for a, b in zip(found, found[1:]) if b[0] == a[0] + 1]
    if len(pairs) < MIN_PAIRS:
        return False
    steps = sum(1 for a, b in pairs if b[1] == a[1] + 1)
    return steps / len(pairs) >= MIN_CONSECUTIVE_FRACTION
