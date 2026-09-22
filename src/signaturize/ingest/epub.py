#!/usr/bin/env python3
"""Extract a single tale from a Project Gutenberg illustrated epub into a
clean HTML body fragment + image set, ready for the pandoc/LaTeX
typesetting stage.

Usage:
    python3 -m signaturize.ingest.epub <epub_path> --slug <slug> [--build-dir build]
"""
import argparse
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup

from ..config import GrayscaleConfig, load_config

SMALL_WORDS = {"of", "the", "a", "an", "and", "in", "on", "at", "for", "to", "by"}


def title_case(raw: str) -> str:
    words = raw.split()
    out = []
    for i, w in enumerate(words):
        lower = w.lower()
        core = lower.strip(".,'’")
        if i > 0 and core in SMALL_WORDS:
            out.append(lower)
            continue
        parts = re.split(r"(-)", w)
        fixed = "".join(p if p == "-" else p[:1].upper() + p[1:].lower() for p in parts)
        out.append(fixed)
    return " ".join(out)


def find_manifest_href(opf: BeautifulSoup, item_id: str) -> str:
    item = opf.find("item", id=item_id)
    if item is None:
        raise SystemExit(f"content.opf: could not find manifest item id={item_id!r}")
    return item["href"]


def extract_author(opf: BeautifulSoup) -> str | None:
    creator = opf.find("dc:creator") or opf.find("creator")
    if creator and creator.text and creator.text.strip():
        return creator.text.strip()
    return None


def unzip_epub(epub_path: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(epub_path) as zf:
        zf.extractall(dest)
    oebps = dest / "OEBPS"
    if not oebps.exists():
        # fall back: some epubs use a different content dir name
        candidates = [p for p in dest.iterdir() if p.is_dir() and (p / "content.opf").exists()]
        if not candidates:
            raise SystemExit(f"Could not locate content.opf under {dest}")
        oebps = candidates[0]
    return oebps


def convert_to_grayscale(src: Path, dst: Path, contrast_stretch: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["convert", str(src), "-colorspace", "Gray", "-auto-level",
         "-contrast-stretch", contrast_stretch, str(dst)],
        check=True,
    )


def copy_image_color(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def clean_image_name(src_href: str) -> str:
    name = Path(src_href).name
    # strip the long numeric hash prefix epub tools prepend, e.g. 198552524033089507_peter04.jpg
    name = re.sub(r"^\d{10,}_", "", name)
    # normalize a weird double extension like peter02.gif.png -> peter02.png
    name = re.sub(r"\.gif\.png$", ".png", name)
    return name


def is_figure_tag(tag) -> bool:
    """True if a <p>/<div> holds only an image (optionally <a>-linked to a
    full-res "wrap" page) and no real text -- covers both epub conventions
    seen so far (<div class="fig"> and <p class="figcenter">)."""
    if tag.name not in ("p", "div"):
        return False
    return tag.find("img") is not None and not tag.get_text(strip=True)


def extract(
    epub_path: Path,
    slug: str,
    build_dir: Path,
    grayscale: GrayscaleConfig,
    author_override: str | None = None,
) -> None:
    story_dir = build_dir / slug
    src_dir = unzip_epub(epub_path, story_dir / "src")

    opf = BeautifulSoup((src_dir / "content.opf").read_text(encoding="utf-8"), "xml")
    body_href = find_manifest_href(opf, "pg-header")
    gutenberg_id = None
    ident = opf.find("dc:identifier") or opf.find("identifier")
    if ident and ident.text:
        m = re.search(r"gutenberg\.org/(\d+)", ident.text)
        if m:
            gutenberg_id = m.group(1)

    author = author_override or extract_author(opf)
    if not author:
        raise SystemExit(
            f"{epub_path}: could not determine author from epub metadata (dc:creator) -- pass --author"
        )

    body_file = src_dir / body_href
    soup = BeautifulSoup(body_file.read_text(encoding="utf-8"), "lxml")

    # Document-order flat list, not sibling/sourceline comparisons -- the
    # source XHTML self-closes <div/> tags, which lxml's HTML parser
    # mis-nests (sourceline ends up None, sibling links get scrambled).
    flat = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "hr", "p", "div"])

    heading_names = {"h1", "h2", "h3", "h4", "h5", "h6"}
    # Gutenberg's ebookmaker consistently tags real content headings with
    # id="pgepubid*" -- more reliable than a specific tag name, since the
    # title heading's level (h1, or h3+h2 split across two tags, etc.)
    # varies between epubs.
    h1_idx = next(
        (i for i, t in enumerate(flat) if t.name in heading_names and t.get("id", "").startswith("pgepubid")),
        None,
    )
    if h1_idx is None:
        raise SystemExit(f"{body_file}: no title heading (id=\"pgepubid*\") found")
    # Some epubs split the title across consecutive heading tags (possibly
    # different levels) instead of using <br/> within one -- gather them.
    title_parts = [flat[h1_idx].get_text(" ", strip=True)]
    j = h1_idx + 1
    while j < len(flat) and flat[j].name in heading_names:
        text = flat[j].get_text(" ", strip=True)
        if text.upper() == "BY":  # byline heading follows directly, no gap
            break
        title_parts.append(text)
        j += 1
    title = title_case(re.sub(r"\s+", " ", " ".join(title_parts)))

    images_out = story_dir / "images"
    if images_out.exists():
        shutil.rmtree(images_out)
    images_out.mkdir(parents=True)

    def resolve_image_href(img_tag) -> str:
        # A thumbnail <img> wrapped in <a href="*.xhtml"> linking to a
        # full-resolution "wrap" page -- follow it and use that image
        # instead of the (lower-res) inline thumbnail.
        parent = img_tag.parent
        if parent is not None and parent.name == "a" and parent.has_attr("href"):
            link_target = src_dir / parent["href"].split("#")[0]
            if link_target.suffix in (".xhtml", ".html", ".htm") and link_target.exists():
                inner = BeautifulSoup(link_target.read_text(encoding="utf-8"), "lxml")
                inner_img = inner.find("img")
                if inner_img is not None and inner_img.has_attr("src"):
                    return str((link_target.parent / inner_img["src"]).resolve().relative_to(src_dir.resolve()))
        return img_tag["src"]

    def copy_image(img_tag) -> str:
        href = resolve_image_href(img_tag)
        clean_name = clean_image_name(href)
        dst = images_out / clean_name
        if grayscale.enabled:
            convert_to_grayscale(src_dir / href, dst, grayscale.contrast_stretch)
        else:
            copy_image_color(src_dir / href, dst)
        return str(dst.resolve())

    # frontispiece: the nearest figure before the title, if any
    frontispiece = None
    prev_fig = next((t for t in reversed(flat[:h1_idx]) if is_figure_tag(t)), None)
    if prev_fig is not None:
        img = prev_fig.find("img")
        if img is not None:
            frontispiece = copy_image(img)

    # story body: everything after the LAST <hr> before "THE END", up to it.
    # Some epubs never spell out "THE END" in the text at all -- the body
    # file (pg-header) holds only real content anyway (the PG license is a
    # separate pg-footer file), so just run to the end of the document.
    # typeset.py always inserts its own "THE END" page regardless.
    end_idx = next(
        (i for i, t in enumerate(flat) if t.get_text(strip=True).upper() == "THE END"),
        len(flat),
    )

    # Some books use <hr> as a mid-story dramatic-pause divider too (e.g.
    # Squirrel Nutkin), not just as a front-matter separator -- so "the
    # last hr before the end" can land deep in the story, truncating
    # everything before it. Front-matter hrs cluster tightly together;
    # take the last hr of that first tight cluster, not the last hr overall.
    hr_indices_before_end = [i for i, t in enumerate(flat[:end_idx]) if t.name == "hr"]
    if hr_indices_before_end:
        cluster = [hr_indices_before_end[0]]
        for idx in hr_indices_before_end[1:]:
            if idx - cluster[-1] <= 6:
                cluster.append(idx)
            else:
                break
        start_idx = cluster[-1] + 1
    else:
        start_idx = 0

    body_tags = []
    for tag in flat[start_idx:end_idx]:
        if is_figure_tag(tag):
            body_tags.append(tag)
        elif tag.name == "p":
            body_tags.append(tag)

    year_match = re.search(r"first published (\d{4})|copyright,? (\d{4})", soup.get_text(), re.IGNORECASE)
    year = next((g for g in (year_match.groups() if year_match else ()) if g), None)

    body_html_parts = []
    for tag in body_tags:
        if is_figure_tag(tag):
            img = tag.find("img")
            path = copy_image(img)
            body_html_parts.append(f'<p class="fig"><img src="{path}"/></p>')
        else:
            for attr in ("style", "class", "id"):
                if tag.has_attr(attr):
                    del tag[attr]
            for child in tag.find_all(True):
                for attr in ("style", "class", "id"):
                    if child.has_attr(attr):
                        del child[attr]
            body_html_parts.append(str(tag))

    story_dir.mkdir(parents=True, exist_ok=True)
    (story_dir / "body.html").write_text(
        "<!DOCTYPE html><html><body>\n" + "\n".join(body_html_parts) + "\n</body></html>",
        encoding="utf-8",
    )

    meta = {
        "title": title,
        "author": author,
        "frontispiece": frontispiece,
        "year": year,
        "gutenberg_id": gutenberg_id,
        "source_epub": str(epub_path.resolve()),
    }
    (story_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Extracted {title!r} by {author} -> {story_dir}")
    print(f"  {len(body_tags)} body elements, frontispiece={'yes' if frontispiece else 'no'}, year={year}, gutenberg_id={gutenberg_id}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epub_path", type=Path)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--build-dir", type=Path, default=Path("build"))
    ap.add_argument("--author", help="override author (default: from epub dc:creator metadata)")
    ap.add_argument("--config", type=Path, help="TOML config file or shipped profile name (default: built-in defaults)")
    args = ap.parse_args()
    config = load_config(args.config)
    extract(args.epub_path, args.slug, args.build_dir, config.grayscale, author_override=args.author)


if __name__ == "__main__":
    main()
