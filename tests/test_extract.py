"""Unit tests for pure helper functions in signaturize.extract."""
from bs4 import BeautifulSoup

from signaturize.ingest.epub import clean_image_name, extract_author, title_case


def test_title_case_handles_small_words():
    assert title_case("THE TALE OF PETER RABBIT") == "The Tale of Peter Rabbit"


def test_title_case_handles_hyphenated_words():
    assert title_case("JEMIMA PUDDLE-DUCK") == "Jemima Puddle-Duck"


def test_clean_image_name_strips_numeric_hash_prefix():
    assert clean_image_name("images/198552524033089507_peter04.jpg") == "peter04.jpg"


def test_clean_image_name_normalizes_double_extension():
    assert clean_image_name("images/peter02.gif.png") == "peter02.png"


def test_extract_author_reads_dc_creator():
    opf = BeautifulSoup(
        "<package><metadata><dc:creator>Beatrix Potter</dc:creator></metadata></package>",
        "xml",
    )
    assert extract_author(opf) == "Beatrix Potter"


def test_extract_author_returns_none_when_absent():
    opf = BeautifulSoup("<package><metadata></metadata></package>", "xml")
    assert extract_author(opf) is None
