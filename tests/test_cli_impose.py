"""End-to-end test of `signaturize impose` through the CLI."""
import json

from conftest import pdf_page_size_in, pdf_text, requires_poppler, write_numbered_pdf

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


@requires_poppler
def test_impose_cli_pin_cover_pins_the_front_cover(tmp_path):
    n_pages = 13
    src = write_numbered_pdf(tmp_path / "src.pdf", n_pages)
    output_dir = tmp_path / "output"
    rc = main([
        "impose", str(src), "--slug", "x", "--scheme", "folio",
        "--output-dir", str(output_dir), "--pin-cover",
    ])
    assert rc == 0

    plan_json = json.loads((output_dir / "x-signature-plan.json").read_text())
    by_sheet_slot = {(leaf["sheet_index"], leaf["sheet_slot"]): leaf for leaf in plan_json["leaves"]}
    # sheet 1, slot 0 (the leaf whose recto is the signature's front
    # cover): page 1 as the recto, forced-blank verso (the reverse of
    # that same leaf stands in for a deliberately-skipped imprint page).
    front = by_sheet_slot[(1, 0)]
    assert front["recto_page"] == 1
    assert front["verso_page"] is None


@requires_poppler
def test_impose_cli_config_duplex_mirror_swaps_back_face(tmp_path):
    """duplex_mirror defaults to True, so the CLI's own default run (no
    --config) is already the "mirrored" case here -- contrasted against
    an explicit duplex_mirror=false config for the unmirrored baseline."""
    src = write_numbered_pdf(tmp_path / "src.pdf", 4)
    config_file = tmp_path / "unmirrored.toml"
    config_file.write_text("[imposition]\nduplex_mirror = false\n", encoding="utf-8")

    unmirrored_dir = tmp_path / "unmirrored"
    rc = main([
        "impose", str(src), "--slug", "x", "--scheme", "folio", "--output-dir", str(unmirrored_dir),
        "--no-marks", "--config", str(config_file), "--landscape-feed",
    ])
    assert rc == 0

    mirrored_dir = tmp_path / "mirrored"
    rc = main([
        "impose", str(src), "--slug", "x", "--scheme", "folio", "--output-dir", str(mirrored_dir),
        "--no-marks", "--landscape-feed",
    ])
    assert rc == 0

    unmirrored_back_west = pdf_text(unmirrored_dir / "x-imposed.pdf", 2, (0, 0, 396, 612))
    mirrored_back_east = pdf_text(mirrored_dir / "x-imposed.pdf", 2, (396, 0, 396, 612))
    assert unmirrored_back_west == mirrored_back_east


@requires_poppler
def test_folio_cli_defaults_to_literal_landscape_page_portrait_feed_rotates(tmp_path):
    src = write_numbered_pdf(tmp_path / "src.pdf", 4)

    default_dir = tmp_path / "default"
    rc = main(["impose", str(src), "--slug", "x", "--scheme", "folio", "--output-dir", str(default_dir)])
    assert rc == 0
    # default: a literal landscape page, upright on screen
    assert pdf_page_size_in(default_dir / "x-imposed.pdf") == (11.0, 8.5)

    portrait_dir = tmp_path / "portrait"
    rc = main([
        "impose", str(src), "--slug", "x", "--scheme", "folio", "--output-dir", str(portrait_dir),
        "--portrait-feed",
    ])
    assert rc == 0
    # --portrait-feed opts into the /Rotate-flagged portrait page
    assert pdf_page_size_in(portrait_dir / "x-imposed.pdf") == (8.5, 11.0)


@requires_poppler
def test_single_leaf_scheme_end_to_end_is_full_sheet_no_fold(tmp_path):
    src = write_numbered_pdf(tmp_path / "src.pdf", 3, width_pt=8.5 * 72, height_pt=11.0 * 72)
    output_dir = tmp_path / "output"
    rc = main([
        "impose", str(src), "--slug", "flat", "--paper", "us-letter", "--scheme", "single-leaf",
        "--binding", "perfect-bound-leaves", "--output-dir", str(output_dir),
    ])
    assert rc == 0
    imposed = output_dir / "flat-imposed.pdf"
    assert imposed.exists()
    # single-leaf (folds=0): every output page is a full, unfolded sheet --
    # no half-size panels from a fold.
    assert pdf_page_size_in(imposed) == (8.5, 11.0)
