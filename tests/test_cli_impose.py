"""End-to-end test of `signaturize impose` through the CLI."""
import json

from conftest import requires_poppler, write_numbered_pdf

from signaturize.cli import main
from signaturize.tools import pdf_page_count


@requires_poppler
def test_impose_cli_writes_all_expected_outputs(tmp_path, capsys):
    src = write_numbered_pdf(tmp_path / "src.pdf", 29)
    output_dir = tmp_path / "output"
    rc = main([
        "impose", str(src), "--slug", "test-book",
        "--scheme", "folio", "--binding", "pamphlet",
        "--output-dir", str(output_dir), "--test-sheet",
    ])
    assert rc == 0

    imposed = output_dir / "test-book-imposed.pdf"
    assert imposed.exists()
    assert pdf_page_count(imposed) == 16  # 8 sheets, folio

    test_sheet = output_dir / "test-book-test-sheet.pdf"
    assert test_sheet.exists()
    assert pdf_page_count(test_sheet) == 2

    plan_json = json.loads((output_dir / "test-book-signature-plan.json").read_text())
    assert plan_json["content_pages"] == 29
    assert plan_json["signature_count"] == 1
    assert len(plan_json["leaves"]) == 8 * 2  # 8 sheets x 2 leaves/sheet (folio)

    printing_md = (output_dir / "test-book-PRINTING.md").read_text()
    assert "test-book-imposed.pdf" in printing_md
    assert "fold" in printing_md.lower()


def test_impose_cli_rejects_unknown_scheme_and_binding(tmp_path, capsys):
    src = write_numbered_pdf(tmp_path / "src.pdf", 4)
    rc = main(["impose", str(src), "--slug", "x", "--binding", "no-such-profile", "--output-dir", str(tmp_path / "out")])
    assert rc == 2
    assert "no-such-profile" in capsys.readouterr().err
