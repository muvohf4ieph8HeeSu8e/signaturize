"""End-to-end test of `signaturize ingest` through the CLI -- the ingest
stage alone, no pandoc/pdflatex/imposition involved."""
import json

from conftest import write_minimal_epub

from signaturize.cli import main


def test_ingest_cli_writes_body_html_and_meta(tmp_path):
    epub = write_minimal_epub(tmp_path / "tiny.epub")
    build_dir = tmp_path / "build"
    rc = main(["ingest", str(epub), "--slug", "tiny", "--build-dir", str(build_dir)])
    assert rc == 0

    story_dir = build_dir / "tiny"
    assert (story_dir / "body.html").exists()
    meta = json.loads((story_dir / "meta.json").read_text())
    assert meta["title"] == "A Tiny Test Tale"
    assert meta["author"] == "Jane Doe"
    assert meta["gutenberg_id"] == "12345"


def test_ingest_cli_honors_author_override(tmp_path):
    epub = write_minimal_epub(tmp_path / "tiny.epub")
    build_dir = tmp_path / "build"
    rc = main([
        "ingest", str(epub), "--slug", "tiny", "--build-dir", str(build_dir),
        "--author", "Someone Else",
    ])
    assert rc == 0
    meta = json.loads((build_dir / "tiny" / "meta.json").read_text())
    assert meta["author"] == "Someone Else"
