import json
from pathlib import Path

import pytest

from policypulse_ingest.blocks import Block
from policypulse_ingest.errors import ContractError
from policypulse_ingest.splitters.headings import Heading
from policypulse_ingest.splitters.hipaa import split_hipaa

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hipaa_pages.json"
CITATION = "HIPAA Privacy Rule Summary"

HEADINGS = (
    Heading("Limiting Uses and Disclosures to the Minimum Necessary", level=1),
    Heading("Minimum Necessary", level=2),
    Heading("Access and Uses", level=2),
    Heading("Disclosures and Requests for Disclosures", level=2),
    Heading("Reasonable Reliance", level=2),
    Heading("Notice and Other Individual Rights", level=1),
    Heading("Privacy Practices Notice", level=2),
    Heading("State Law", level=1),
    Heading("Preemption", level=2),
    Heading("Exception Determination", level=2),
    Heading("Enforcement and Penalties for Noncompliance", level=1),
    Heading("Compliance", level=2),
    Heading("Civil Money Penalties", level=2),
    Heading("Criminal Penalties", level=2),
    Heading("Compliance Dates", level=1),
    Heading("Compliance Schedule", level=2),
    Heading("Small Health Plans", level=2),
    Heading("Copies of the Rule & Related Materials", level=1),
    Heading("End Notes", level=1, keep=False),
)


def load_pages() -> list[str]:
    """Pages keyed by their 1-based PDF page number, padded so list index plus one is the page."""
    by_page = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pages = [""] * max(int(number) for number in by_page)
    for number, text in by_page.items():
        pages[int(number) - 1] = text
    return pages


@pytest.fixture
def blocks() -> list[Block]:
    pages = load_pages()
    header = "OCR Privacy Rule Summary   19   Last Revised 05/03"
    end_notes_page = "\n".join([header, "End Notes", "", "1 Pub. L. 104-191."])
    pages.append(end_notes_page)
    return split_hipaa(pages, HEADINGS)


def only(blocks: list[Block], label: str) -> Block:
    matching = [block for block in blocks if block.label == label]
    assert len(matching) == 1, f"expected one block labeled {label!r}, found {len(matching)}"
    return matching[0]


def test_labels_the_minimum_necessary_section_with_heading_and_page(blocks: list[Block]):
    # Arrange / Act
    block = only(blocks, f"{CITATION}, Minimum Necessary, p. 12")

    # Assert
    assert block.text.startswith("A central aspect of the Privacy Rule is the principle")
    assert "reasonable efforts to use, disclose, and request only the minimum" in block.text
    assert block.page == 12
    assert block.breadcrumb == (
        CITATION,
        "Limiting Uses and Disclosures to the Minimum Necessary",
        "Minimum Necessary",
    )
    assert block.doc_id == "hipaa"


def test_keeps_the_exceptions_paragraph_with_the_minimum_necessary_block(blocks: list[Block]):
    # Arrange / Act
    block = only(blocks, f"{CITATION}, Minimum Necessary, p. 12")

    # Assert
    assert "not imposed in any of the following circumstances" in block.text
    assert "(a) disclosure to or a request by a health care provider for treatment" in block.text
    assert "Access and Uses." not in block.text


def test_separates_criminal_from_civil_penalties(blocks: list[Block]):
    # Arrange / Act
    criminal = only(blocks, f"{CITATION}, Criminal Penalties, p. 20")
    civil = only(blocks, f"{CITATION}, Civil Money Penalties, p. 19")

    # Assert
    assert "$250,000" in criminal.text
    assert "$250,000" not in civil.text
    assert "$25,000" in civil.text


def test_labels_a_page_for_the_heading_not_for_the_text_it_runs_onto(blocks: list[Block]):
    # Arrange / Act
    labels = [block.label for block in blocks]

    # Assert
    assert f"{CITATION}, Compliance Schedule, p. 20" in labels
    assert f"{CITATION}, Preemption, p. 19" in labels


def test_finds_a_section_heading_that_wraps_over_several_lines(blocks: list[Block]):
    # Arrange / Act
    block = only(blocks, f"{CITATION}, Copies of the Rule & Related Materials, p. 20")

    # Assert
    assert block.text.startswith("The entire Privacy Rule, as well as guidance")


def test_drops_running_page_headers_and_the_end_notes(blocks: list[Block]):
    # Arrange / Act
    texts = " ".join(block.text for block in blocks)

    # Assert
    assert "OCR Privacy Rule Summary" not in texts
    assert "Last Revised" not in texts
    assert "Pub. L. 104-191" not in texts
    assert not any("End Notes" in block.label for block in blocks)


def test_joins_wrapped_lines_and_keeps_bullets_on_their_own_lines(blocks: list[Block]):
    # Arrange / Act
    exception = only(blocks, f"{CITATION}, Exception Determination, p. 19")

    # Assert
    assert "\n• Is necessary to prevent fraud and abuse" in exception.text
    assert exception.text.startswith("In addition, preemption of a contrary State law")


def test_fails_when_an_expected_heading_is_missing():
    # Arrange
    headings = (*HEADINGS[:-1], Heading("Genetic Information", level=2), HEADINGS[-1])

    # Act / Assert
    with pytest.raises(ContractError, match="Genetic Information"):
        split_hipaa(load_pages(), headings)
