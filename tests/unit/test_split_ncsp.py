from collections.abc import Callable

import pytest

from policypulse_ingest.blocks import Block
from policypulse_ingest.splitters.ncsp import split_ncsp


@pytest.fixture
def blocks(load_fixture_pages: Callable[[str], list[str]]) -> list[Block]:
    return split_ncsp(load_fixture_pages("ncsp_excerpt.txt"))


def only(blocks: list[Block], label: str) -> Block:
    matching = [block for block in blocks if block.label == label]
    assert len(matching) == 1, f"expected one block labeled {label!r}, found {len(matching)}"
    return matching[0]


def test_labels_each_numbered_objective(blocks: list[Block]):
    # Arrange / Act
    objective_8 = only(blocks, "NCSP 2013, Objective 8")

    # Assert
    assert "500,000" in objective_8.text
    assert objective_8.text.startswith("To create a workforce")
    assert objective_8.breadcrumb == ("NCSP 2013", "Objectives", "Objective 8")
    assert objective_8.doc_id == "ncsp"


def test_labels_strategy_items_with_the_strategy_title_in_the_breadcrumb(blocks: list[Block]):
    # Arrange / Act
    item = only(blocks, "NCSP 2013, Strategy E, item 2")

    # Assert
    assert "CERT-In" in item.text
    assert item.breadcrumb == (
        "NCSP 2013",
        "Strategies",
        "Strategy E Creating mechanisms for security threat early warning, "
        "vulnerability management and response to security threats",
        "Item 2",
    )


def test_labels_a_strategy_without_items_by_the_strategy_alone(blocks: list[Block]):
    # Arrange / Act
    strategy_n = only(blocks, "NCSP 2013, Strategy N")

    # Assert
    assert strategy_n.text.startswith("To adopt a prioritized approach")


def test_keeps_objective_10_separate_from_objective_9(blocks: list[Block]):
    # Arrange
    objective_9 = only(blocks, "NCSP 2013, Objective 9")
    objective_10 = only(blocks, "NCSP 2013, Objective 10")

    # Act
    in_objective_10 = ("storage" in objective_10.text, "transit" in objective_10.text)
    in_objective_9 = ("storage" in objective_9.text, "transit" in objective_9.text)

    # Assert
    assert in_objective_10 == (True, True)
    assert in_objective_9 == (False, False)


def test_labels_preamble_paragraphs_vision_mission_and_operationalisation(blocks: list[Block]):
    # Arrange / Act
    labels = [block.label for block in blocks]

    # Assert
    assert "NCSP 2013, Preamble, para 1" in labels
    assert "NCSP 2013, Preamble, para 2" in labels
    assert only(blocks, "NCSP 2013, Vision").text.startswith("To build a secure and resilient")
    assert only(blocks, "NCSP 2013, Mission").text.startswith("To protect information")
    assert only(blocks, "NCSP 2013, Operationalisation").text.startswith("This policy shall be")


def test_keeps_the_ordered_items_of_a_strategy_in_document_order(blocks: list[Block]):
    # Arrange / Act
    prefix = "NCSP 2013, Strategy G"
    strategy_g = [block.label for block in blocks if block.label.startswith(prefix)]

    # Assert
    assert strategy_g == ["NCSP 2013, Strategy G, item 1", "NCSP 2013, Strategy G, item 2"]


def test_drops_page_headers_and_footnote_lines(blocks: list[Block]):
    # Arrange / Act
    texts = " ".join(block.text for block in blocks)

    # Assert
    assert "Page 4 of 9" not in texts
    assert "ISO / IEC 27032" not in texts


def test_joins_wrapped_lines_into_one_text_per_block(blocks: list[Block]):
    # Arrange / Act
    item = only(blocks, "NCSP 2013, Strategy G, item 2")

    # Assert
    assert "\n" not in item.text
    assert item.text.endswith("protection in the country.")
