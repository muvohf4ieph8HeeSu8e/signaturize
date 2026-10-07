"""End-to-end test of `signaturize typeset` through the CLI -- the
typeset stage alone, run on a prior `signaturize ingest` run's output
(mirrors how test_cli_impose.py exercises `impose` alone)."""
from conftest import pdf_page_size_in, pdf_text, requires_latex, requires_poppler, write_minimal_epub

from signaturize.cli import main
from signaturize.tools import pdf_page_count


@requires_latex
@requires_poppler
def test_typeset_cli_produces_a_trim_pdf(tmp_path):
    epub = write_minimal_epub(tmp_path / "tiny.epub")
    build_dir = tmp_path / "build"
    output_dir = tmp_path / "output"
    preview_dir = tmp_path / "preview"

    rc = main(["ingest", str(epub), "--slug", "tiny", "--build-dir", str(build_dir)])
    assert rc == 0

    rc = main([
        "typeset", "tiny",
        "--build-dir", str(build_dir), "--output-dir", str(output_dir),
        "--preview-dir", str(preview_dir),
    ])
    assert rc == 0

    out_pdf = output_dir / "tiny-trimmed.pdf"
    assert out_pdf.exists()
    assert pdf_page_count(out_pdf) >= 1
    assert any((preview_dir / "tiny" / "reading-order").glob("page-*.png"))


def test_typeset_cli_errors_without_a_prior_ingest(tmp_path):
    rc = main([
        "typeset", "tiny",
        "--build-dir", str(tmp_path / "build"), "--output-dir", str(tmp_path / "output"),
    ])
    assert rc == 2


@requires_latex
@requires_poppler
def test_typeset_cli_paper_and_scheme_control_trim_size(tmp_path):
    epub = write_minimal_epub(tmp_path / "tiny.epub")
    build_dir = tmp_path / "build"
    rc = main(["ingest", str(epub), "--slug", "tiny", "--build-dir", str(build_dir)])
    assert rc == 0

    # single-leaf: unfolded, trim == the full sheet.
    flat_dir = tmp_path / "flat"
    rc = main([
        "typeset", "tiny", "--build-dir", str(build_dir), "--output-dir", str(flat_dir),
        "--paper", "us-letter", "--scheme", "single-leaf",
    ])
    assert rc == 0
    assert pdf_page_size_in(flat_dir / "tiny-trimmed.pdf") == (8.5, 11.0)

    # folio: one center fold, trim == half the (landscape-fed) sheet.
    folio_dir = tmp_path / "folio"
    rc = main([
        "typeset", "tiny", "--build-dir", str(build_dir), "--output-dir", str(folio_dir),
        "--paper", "us-letter", "--scheme", "folio",
    ])
    assert rc == 0
    assert pdf_page_size_in(folio_dir / "tiny-trimmed.pdf") == (5.5, 8.5)


@requires_latex
@requires_poppler
def test_typeset_cli_page_numbers_flag_numbers_the_body_only(tmp_path):
    epub = write_minimal_epub(tmp_path / "tiny.epub")
    build_dir = tmp_path / "build"
    rc = main(["ingest", str(epub), "--slug", "tiny", "--build-dir", str(build_dir)])
    assert rc == 0

    numbered_dir = tmp_path / "numbered"
    rc = main([
        "typeset", "tiny", "--build-dir", str(build_dir), "--output-dir", str(numbered_dir), "--page-numbers",
    ])
    assert rc == 0
    numbered_pdf = numbered_dir / "tiny-trimmed.pdf"
    # page 1 = title (unnumbered), page 2 = the (only) body page --
    # numbered "1", restarting regardless of the title page ahead of it.
    assert "1" not in pdf_text(numbered_pdf, 1).split()
    assert "1" in pdf_text(numbered_pdf, 2).split()

    plain_dir = tmp_path / "plain"
    rc = main(["typeset", "tiny", "--build-dir", str(build_dir), "--output-dir", str(plain_dir)])
    assert rc == 0
    plain_pdf = plain_dir / "tiny-trimmed.pdf"
    assert "1" not in pdf_text(plain_pdf, 2).split()
