from collections.abc import Callable

import pytest

from policypulse_ingest.blocks import Block
from policypulse_ingest.splitters.registration_api import split_registration_api

CITATION = "Registration API"

NUMBERED_PDF_PAGES = [
    "\n".join(
        [
            "Sample Registration API",
            "This synthetic document stands in for the real specification.",
            "1 Duplicate detection",
            "An incoming customer is compared with stored customers",
            "on a normalized key.",
            "2 Fuzzy screening",
            "A model scores the remaining candidates.",
            "2.1 Timeout",
            "A screening call that exceeds its limit falls back to the exact comparison.",
        ]
    ),
    "\n".join(
        [
            "2.2 Candidate cap",
            "A fixed number of candidates is sent in each call.",
            "Up to 5 candidates are named in the text of this section.",
        ]
    ),
]


@pytest.fixture
def markdown_blocks(load_fixture_pages: Callable[[str], list[str]]) -> list[Block]:
    return split_registration_api(load_fixture_pages("registration_api_spec.md"))


def by_label(blocks: list[Block]) -> dict[str, Block]:
    return {block.label: block for block in blocks}


def test_builds_labels_from_the_heading_path(markdown_blocks: list[Block]):
    # Arrange / Act
    labels = [block.label for block in markdown_blocks]

    # Assert
    assert labels == [
        "Registration API, Overview",
        "Registration API, Duplicate detection",
        "Registration API, Fuzzy screening",
        "Registration API, Fuzzy screening > Timeout",
        "Registration API, Fuzzy screening > Candidate cap",
    ]


def test_breadcrumb_lists_the_heading_path_under_the_citation_name(markdown_blocks: list[Block]):
    # Arrange / Act
    timeout = by_label(markdown_blocks)["Registration API, Fuzzy screening > Timeout"]

    # Assert
    assert timeout.breadcrumb == (CITATION, "Fuzzy screening", "Timeout")
    assert timeout.doc_id == "registration_api"


def test_ignores_hash_lines_inside_fenced_code(markdown_blocks: list[Block]):
    # Arrange / Act
    blocks = by_label(markdown_blocks)
    detection = blocks["Registration API, Duplicate detection"]

    # Assert
    assert not any("looks like a heading" in label for label in blocks)
    assert "# this line looks like a heading but sits inside a code fence" in detection.text
    assert "After the fence the section text continues." in detection.text


def test_keeps_markdown_line_structure_inside_a_section(markdown_blocks: list[Block]):
    # Arrange / Act
    detection = by_label(markdown_blocks)["Registration API, Duplicate detection"]

    # Assert
    assert "```text\n# this line" in detection.text
    assert "key = normalize(value)\n```" in detection.text


def test_splits_a_numbered_heading_pdf_text_the_same_way(markdown_blocks: list[Block]):
    # Arrange
    markdown_labels = {block.label for block in markdown_blocks} - {"Registration API, Overview"}

    # Act
    pdf_blocks = split_registration_api(NUMBERED_PDF_PAGES)

    # Assert
    assert {block.label for block in pdf_blocks} - {"Registration API, Overview"} == markdown_labels


def test_joins_the_wrapped_lines_of_a_pdf_section_and_continues_across_pages():
    # Arrange / Act
    blocks = by_label(split_registration_api(NUMBERED_PDF_PAGES))

    # Assert
    detection = blocks["Registration API, Duplicate detection"]
    cap = blocks["Registration API, Fuzzy screening > Candidate cap"]
    assert detection.text == (
        "An incoming customer is compared with stored customers on a normalized key."
    )
    assert cap.text.endswith("Up to 5 candidates are named in the text of this section.")


def test_does_not_read_a_numbered_sentence_as_a_heading():
    # Arrange
    pages = [
        "\n".join(
            [
                "1 Limits",
                "The service applies these limits:",
                "5 candidates are sent to the model in each call.",
            ]
        )
    ]

    # Act
    blocks = split_registration_api(pages)

    # Assert
    assert [block.label for block in blocks] == ["Registration API, Limits"]
    assert "5 candidates are sent to the model in each call." in blocks[0].text
