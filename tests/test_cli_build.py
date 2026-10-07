"""End-to-end test of `signaturize build` through the CLI -- exercises the
full ingest -> pandoc -> typeset -> pdflatex -> impose pipeline against a
minimal synthetic epub. `build` is pure composition of `ingest`,
`typeset`, and `impose` (see cli.py's build_booklet()) -- no imposition
or typesetting logic of its own -- so this confirms it produces exactly
the artifact set those three commands' own stage functions produce."""
from conftest import requires_latex, requires_poppler, write_minimal_epub

from signaturize.cli import main


@requires_latex
@requires_poppler
def test_build_cli_produces_all_imposition_outputs(tmp_path):
    epub = write_minimal_epub(tmp_path / "tiny.epub")
    rc = main([
        "build", str(epub), "--slug", "tiny",
        "--build-dir", str(tmp_path / "build"),
        "--preview-dir", str(tmp_path / "preview"),
        "--output-dir", str(tmp_path / "output"),
    ])
    assert rc == 0

    out = tmp_path / "output"
    assert (out / "tiny-trimmed.pdf").exists()
    assert (out / "tiny-imposed.pdf").exists()
    assert (out / "tiny-test-sheet.pdf").exists()
    assert (out / "tiny-signature-plan.json").exists()
    assert (out / "tiny-PRINTING.md").exists()
