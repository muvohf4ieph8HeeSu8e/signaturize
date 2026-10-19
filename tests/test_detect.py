"""has_printed_page_numbers(): impose skips its own per-panel page-number
label when the source PDF already prints folios."""
import pikepdf
import pytest

from conftest import pdf_text, requires_poppler, write_numbered_pdf
from signaturize.cli import main
from signaturize.impose.detect import has_printed_page_numbers


def write_footer_pdf(path, labels, width_pt=396, height_pt=612):
    """A PDF with a body line on every page and, where the label is not
    None, that label as a centred footer 40pt from the bottom."""
    pdf = pikepdf.new()
    font = pdf.make_indirect(
        pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
    )
    for i, label in enumerate(labels, start=1):
        body = f"BT /F1 12 Tf 60 400 Td (Body text of page {i * 100}) Tj ET\n"
        foot = f"BT /F1 9 Tf 190 40 Td ({label}) Tj ET\n" if label is not None else ""
        page = pdf.add_blank_page(page_size=(width_pt, height_pt))
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        page.Contents = pdf.make_stream((body + foot).encode())
    pdf.save(path)
    return path


@requires_poppler
def test_footer_folios_are_detected(tmp_path):
    src = write_footer_pdf(tmp_path / "n.pdf", [str(i) for i in range(1, 9)])
    assert has_printed_page_numbers(src)


@requires_poppler
def test_unnumbered_front_matter_and_restart_still_detected(tmp_path):
    labels = [None, None, None] + [str(i) for i in range(1, 9)]
    assert has_printed_page_numbers(write_footer_pdf(tmp_path / "n.pdf", labels))


@requires_poppler
def test_pdf_without_footers_is_not_numbered(tmp_path):
    assert not has_printed_page_numbers(write_footer_pdf(tmp_path / "n.pdf", [None] * 6))


@requires_poppler
def test_big_centred_number_is_not_a_folio(tmp_path):
    # write_numbered_pdf puts each page's number mid-page, not in a margin
    assert not has_printed_page_numbers(write_numbered_pdf(tmp_path / "n.pdf", 8))


@requires_poppler
def test_unrelated_edge_numbers_are_not_a_folio(tmp_path):
    labels = ["7", "42", "3", "19", "88", "5"]
    assert not has_printed_page_numbers(write_footer_pdf(tmp_path / "n.pdf", labels))


@requires_poppler
def test_impose_skips_overlay_for_numbered_source_and_force_overrides(tmp_path, capsys):
    src = write_footer_pdf(tmp_path / "n.pdf", [str(i) for i in range(1, 5)])

    def footer_text(out_dir, *extra):
        rc = main(["impose", str(src), "--slug", "x", "--scheme", "folio", "--no-pin-cover",
                   "--output-dir", str(out_dir), *extra])
        assert rc == 0
        # bottom strip of both panels: the 16pt overlay sits
        # below the 40pt footer; crop the bottom 72pt of the page
        return pdf_text(out_dir / "x-imposed.pdf", 1, (0, 540, 792, 72))

    auto = tmp_path / "auto"
    auto_text = footer_text(auto)
    assert "skipping the per-panel page-number overlay" in capsys.readouterr().out

    forced = tmp_path / "forced"
    forced_text = footer_text(forced, "--page-overlay", "on")

    # forced draws an extra label per panel, so it has more digits in the strip
    assert sum(c.isdigit() for c in forced_text) > sum(c.isdigit() for c in auto_text)
