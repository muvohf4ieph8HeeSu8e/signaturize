"""Unit tests for pure helper functions in signaturize.typeset."""
import pytest

from signaturize.typeset.pamphlet import cover_sequence, latex_escape


def test_latex_escape_escapes_ampersand_percent_hash():
    assert latex_escape("Tom & Jerry 100% #1") == r"Tom \& Jerry 100\% \#1"


def test_latex_escape_escapes_backslash():
    assert latex_escape("a\\b") == r"a\textbackslash{}b"


def test_cover_sequence_pins_page_one_and_forces_a_blank_second_slot():
    assert cover_sequence(1) == [1, None]
    assert cover_sequence(2) == [1, None, 2]
    assert cover_sequence(5) == [1, None, 2, 3, 4, 5]


def test_cover_sequence_places_every_page_exactly_once():
    seq = cover_sequence(10)
    placed = [p for p in seq if p is not None]
    assert sorted(placed) == list(range(1, 11))


def test_cover_sequence_rejects_nonpositive_page_count():
    with pytest.raises(ValueError):
        cover_sequence(0)
