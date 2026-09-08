"""Unit tests for pure helper functions in signaturize.typeset."""
from signaturize.typeset import latex_escape


def test_latex_escape_escapes_ampersand_percent_hash():
    assert latex_escape("Tom & Jerry 100% #1") == r"Tom \& Jerry 100\% \#1"


def test_latex_escape_escapes_backslash():
    assert latex_escape("a\\b") == r"a\textbackslash{}b"
