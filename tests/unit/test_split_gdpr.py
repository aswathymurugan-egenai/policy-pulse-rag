from collections.abc import Callable

import pytest

from policypulse_ingest.blocks import Block
from policypulse_ingest.splitters.gdpr import split_gdpr

FOOTER = "4.5.2016 L 119/1 Official Journal of the European Union EN"


@pytest.fixture
def blocks(load_fixture_pages: Callable[[str], list[str]]) -> list[Block]:
    return split_gdpr(load_fixture_pages("gdpr_excerpt.txt"))


def only(blocks: list[Block], label: str) -> Block:
    matching = [block for block in blocks if block.label == label]
    assert len(matching) == 1, f"expected one block labeled {label!r}, found {len(matching)}"
    return matching[0]


def labels(blocks: list[Block]) -> list[str]:
    return [block.label for block in blocks]


def synthetic_article(
    *body_lines: str, title: str = "Sample article", number: int = 7
) -> list[str]:
    """One page holding the numbered article and the given body lines, then the running footer."""
    lines = [
        "Whereas:",
        "HAVE ADOPTED THIS REGULATION:",
        "CHAPTER I",
        "Sample chapter",
        f"Article {number}",
        title,
    ]
    return ["\n".join([*lines, *body_lines, FOOTER])]


def test_labels_article_33_paragraph_1_with_its_title_in_the_breadcrumb(blocks: list[Block]):
    # Arrange / Act
    block = only(blocks, "GDPR Art. 33(1)")

    # Assert
    assert block.breadcrumb == (
        "GDPR",
        "Chapter IV Controller and processor",
        "Section 2 Security of personal data",
        "Article 33 Notification of a personal data breach to the supervisory authority",
        "Paragraph 1",
    )
    assert block.text.startswith("In the case of a personal data breach")
    assert "72 hours" in block.text
    assert block.doc_id == "gdpr"


def test_labels_points_under_a_paragraph(blocks: list[Block]):
    # Arrange / Act
    block = only(blocks, "GDPR Art. 5(1)(c)")

    # Assert
    assert "limited to what is necessary" in block.text
    assert block.breadcrumb[-2:] == ("Paragraph 1", "Point (c)")


def test_keeps_the_lead_in_of_a_paragraph_apart_from_its_points(blocks: list[Block]):
    # Arrange / Act
    lead_in = only(blocks, "GDPR Art. 5(1)")

    # Assert
    assert lead_in.text == "Personal data shall be:"


def test_labels_article_4_definitions(blocks: list[Block]):
    # Arrange / Act
    first = only(blocks, "GDPR Art. 4(1)")
    second = only(blocks, "GDPR Art. 4(2)")

    # Assert
    assert first.text.startswith("‘personal data’ means")
    assert second.text.startswith("‘processing’ means")
    assert only(blocks, "GDPR Art. 4").text == "For the purposes of this Regulation:"


def test_labels_recitals_in_sequence(blocks: list[Block]):
    # Arrange / Act
    recital_85 = only(blocks, "GDPR Recital 85")
    recital_86 = only(blocks, "GDPR Recital 86")

    # Assert
    assert recital_85.text.startswith("A personal data breach may")
    assert recital_86.text.startswith("The controller should communicate")
    assert recital_85.breadcrumb == ("GDPR", "Recital 85")


def test_drops_a_footnote_that_breaks_the_recital_sequence(blocks: list[Block]):
    # Arrange / Act
    texts = " ".join(block.text for block in blocks)

    # Assert
    assert "Commission Recommendation of 6 May 2003" not in texts


def test_drops_a_footnote_even_when_its_number_continues_the_recital_sequence():
    # Arrange
    first_page = "\n".join(
        ["Whereas:", "(1)  First recital text.", FOOTER, "(2) OJ C 229, 31.7.2012, p. 90."]
    )
    second_page = "\n".join(["HAVE ADOPTED THIS REGULATION:", FOOTER])

    # Act
    blocks = split_gdpr([first_page, second_page])

    # Assert
    assert labels(blocks) == ["GDPR Recital 1"]
    assert blocks[0].text == "First recital text."


def test_strips_official_journal_running_headers(blocks: list[Block]):
    # Arrange / Act
    texts = " ".join(block.text for block in blocks)

    # Assert
    assert "Official Journal of the European Union" not in texts
    assert "L 119/" not in texts


def test_keeps_article_83_paragraphs_4_and_5_in_separate_blocks(blocks: list[Block]):
    # Arrange / Act
    paragraph_4 = only(blocks, "GDPR Art. 83(4)")
    paragraph_5 = only(blocks, "GDPR Art. 83(5)")
    paragraph_6 = only(blocks, "GDPR Art. 83(6)")

    # Assert
    assert "10 000 000 EUR" in paragraph_4.text
    assert "20 000 000 EUR" not in paragraph_4.text
    assert "20 000 000 EUR" in paragraph_5.text
    assert "10 000 000 EUR" not in paragraph_5.text
    assert "20 000 000 EUR" in paragraph_6.text


def test_joins_wrapped_lines_and_removes_soft_hyphens():
    # Arrange
    pages = synthetic_article("1. Measures of pseudonymi­", "sation apply to the", "controller.")

    # Act
    blocks = split_gdpr(pages)

    # Assert
    assert blocks[0].label == "GDPR Art. 7(1)"
    assert blocks[0].text == "Measures of pseudonymisation apply to the controller."


def test_treats_i_as_a_point_only_after_point_h():
    # Arrange
    pages = synthetic_article(
        "1. The controller shall consider:",
        "(a)  the following items:",
        "(i) a roman sub-point;",
        "(ii) another roman sub-point;",
        "(b)  second point;",
        "(c)  third point;",
        "(d)  fourth point;",
        "(e)  fifth point;",
        "(f)  sixth point;",
        "(g)  seventh point;",
        "(h)  eighth point;",
        "(i)  ninth point.",
    )

    # Act
    blocks = split_gdpr(pages)

    # Assert
    assert labels(blocks)[-1] == "GDPR Art. 7(1)(i)"
    assert labels(blocks).count("GDPR Art. 7(1)(a)") == 1
    point_a = only(blocks, "GDPR Art. 7(1)(a)")
    assert "(i) a roman sub-point; (ii) another roman sub-point;" in point_a.text


def test_ignores_a_numbered_line_that_does_not_continue_the_paragraph_sequence():
    # Arrange
    pages = synthetic_article(
        "1. First paragraph text that continues",
        "5. on a wrapped line.",
        "2. Second paragraph.",
    )

    # Act
    blocks = split_gdpr(pages)

    # Assert
    assert labels(blocks) == ["GDPR Art. 7(1)", "GDPR Art. 7(2)"]
    assert blocks[0].text == "First paragraph text that continues 5. on a wrapped line."


def test_stops_at_the_closing_signature_block():
    # Arrange
    pages = synthetic_article(
        "1. Last paragraph.",
        "This Regulation shall be binding in its entirety.",
        "Done at Brussels, 27 April 2016.",
        "For the European Parliament",
    )

    # Act
    blocks = split_gdpr(pages)

    # Assert
    assert "Brussels" not in blocks[-1].text
    assert "For the European Parliament" not in blocks[-1].text


def test_labels_points_inside_a_definition_with_the_definition_number():
    # Arrange
    pages = synthetic_article(
        "For the purposes of this Regulation:",
        "(1) ‘first term’ means the first meaning;",
        "(2) ‘second term’ means either:",
        "(a)  the first alternative; or",
        "(b)  the second alternative;",
        "(3) ‘third term’ means the third meaning.",
        number=4,
    )

    # Act
    blocks = split_gdpr(pages)

    # Assert
    assert labels(blocks) == [
        "GDPR Art. 4",
        "GDPR Art. 4(1)",
        "GDPR Art. 4(2)",
        "GDPR Art. 4(2)(a)",
        "GDPR Art. 4(2)(b)",
        "GDPR Art. 4(3)",
    ]
    assert only(blocks, "GDPR Art. 4(2)(b)").breadcrumb[-2:] == ("Definition 2", "Point (b)")
