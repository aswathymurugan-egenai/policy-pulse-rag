from collections.abc import Callable
from dataclasses import replace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from policypulse_ingest.blocks import Block
from policypulse_ingest.errors import ContractError
from policypulse_ingest.splitters.headings import SUBSECTION, Heading
from policypulse_ingest.splitters.road_safety import ROAD_SAFETY_HEADINGS, split_road_safety

CITATION = "Road Safety Policy"
LONG_TITLE = (
    "Strengthening Enabling Legal, Institutional and Financial Environment for Road Safety"
)
TWO_SECTIONS = (Heading("Preamble"), Heading("Policy Statements"))


@pytest.fixture
def pages(load_fixture_pages: Callable[[str], list[str]]) -> list[str]:
    return load_fixture_pages("road_safety_excerpt.txt")


@pytest.fixture
def blocks(pages: list[str]) -> list[Block]:
    return split_road_safety(pages, ROAD_SAFETY_HEADINGS)


def only(blocks: list[Block], label: str) -> Block:
    matching = [block for block in blocks if block.label == label]
    assert len(matching) == 1, f"expected one block labeled {label!r}, found {len(matching)}"
    return matching[0]


def test_labels_the_unnumbered_opening_text_as_introduction(blocks: list[Block]):
    # Arrange / Act
    introduction = only(blocks, f"{CITATION}, Introduction")

    # Assert
    assert "Union Cabinet on 15.03.2010 approved National Road Safety Policy" in introduction.text
    assert "Shri S. Sundar, Former Secretary (MoST)" in introduction.text
    assert "report in February, 2007" in introduction.text
    assert not introduction.text.startswith("National Road Safety Policy ")
    assert introduction.doc_id == "road_safety"


def test_labels_the_funding_and_oversight_text_by_its_section_heading(blocks: list[Block]):
    # Arrange / Act
    section = only(blocks, f"{CITATION}, Implementation Strategy")

    # Assert
    assert "National Road Safety Board" in section.text
    assert "National Road Safety Fund" in section.text
    assert "cess on gasoline and diesel" in section.text
    assert section.text.startswith("The Government has decided to establish a dedicated agency")
    assert section.breadcrumb == (CITATION, "Implementation Strategy")


def test_nests_each_policy_statement_under_the_policy_statements_heading(blocks: list[Block]):
    # Arrange / Act
    statement = only(blocks, f"{CITATION}, Safer Drivers")

    # Assert
    assert statement.breadcrumb == (CITATION, "Policy Statements", "Safer Drivers")
    assert statement.text.startswith("The Government will strengthen the system of driver")


def test_drops_the_repeated_layout_text_the_pdf_extracts_twice(blocks: list[Block]):
    # Arrange
    infrastructure = only(blocks, f"{CITATION}, Ensure Safer Road Infrastructure")
    vulnerable = only(blocks, f"{CITATION}, Safety of Vulnerable Road Users")

    # Act
    framework_mentions = infrastructure.text.lower().count("national framework to establish")

    # Assert
    assert framework_mentions == 1
    assert infrastructure.text.endswith("transport system will be encouraged.")
    assert "framework" not in vulnerable.text
    assert vulnerable.text.endswith("highway and traffic engineers.")


def test_finds_a_heading_that_wraps_over_two_lines(blocks: list[Block]):
    # Arrange
    title = (
        "Strengthening Enabling Legal, Institutional and Financial "
        "Environment for Road Safety"
    )

    # Act
    section = only(blocks, f"{CITATION}, {title}")

    # Assert
    assert section.text.startswith("The Government will take appropriate measures to ensure")


def test_turns_private_use_bullets_into_bullet_lines(blocks: list[Block]):
    # Arrange / Act
    preamble = only(blocks, f"{CITATION}, Preamble")

    # Assert
    assert preamble.text.count("\n") == 2
    assert all(line.startswith("• ") for line in preamble.text.split("\n"))


def test_emits_one_block_per_heading_plus_the_introduction(blocks: list[Block]):
    # Arrange / Act
    labels = [block.label for block in blocks]

    # Assert
    assert len(labels) == len(ROAD_SAFETY_HEADINGS) + 1
    assert len(set(labels)) == len(labels)


def test_fails_when_an_expected_heading_is_missing(pages: list[str]):
    # Arrange
    headings = (*ROAD_SAFETY_HEADINGS, Heading("Toll Policy", level=1))

    # Act / Assert
    with pytest.raises(ContractError, match="Toll Policy"):
        split_road_safety(pages, headings)


def test_emits_the_introduction_first_then_each_heading_in_reading_order(blocks: list[Block]):
    # Arrange
    expected = [f"{CITATION}, Introduction"]
    expected += [f"{CITATION}, {heading.title}" for heading in ROAD_SAFETY_HEADINGS]

    # Act
    labels = [block.label for block in blocks]

    # Assert
    assert labels == expected


def test_uses_the_registered_headings_when_none_are_given(pages: list[str]):
    # Arrange / Act
    by_default = split_road_safety(pages)

    # Assert
    assert by_default == split_road_safety(pages, ROAD_SAFETY_HEADINGS)


@pytest.mark.parametrize(
    ("title", "page"),
    [
        ("Introduction", 1),
        ("Preamble", 1),
        ("Establish a Road Safety Information Database", 1),
        ("Ensure Safer Road Infrastructure", 2),
        ("Road Traffic Safety Education and Training", 2),
        ("Enforcement of Safety Laws", 3),
        (LONG_TITLE, 3),
        ("Implementation Strategy", 3),
    ],
)
def test_records_the_page_where_each_block_starts(blocks: list[Block], title: str, page: int):
    # Arrange / Act
    block = only(blocks, f"{CITATION}, {title}")

    # Assert
    assert block.page == page


@pytest.mark.parametrize("title", ["Preamble", "Policy Statements"])
def test_gives_a_top_level_heading_a_two_part_breadcrumb(blocks: list[Block], title: str):
    # Arrange / Act
    block = only(blocks, f"{CITATION}, {title}")

    # Assert
    assert block.breadcrumb == (CITATION, title)


@pytest.mark.parametrize(
    "title",
    [heading.title for heading in ROAD_SAFETY_HEADINGS if heading.level == SUBSECTION],
)
def test_nests_every_policy_statement_under_the_policy_statements_heading(
    blocks: list[Block], title: str
):
    # Arrange / Act
    block = only(blocks, f"{CITATION}, {title}")

    # Assert
    assert block.breadcrumb == (CITATION, "Policy Statements", title)


def test_keeps_only_the_lead_in_sentence_in_the_policy_statements_block(blocks: list[Block]):
    # Arrange / Act
    block = only(blocks, f"{CITATION}, Policy Statements")

    # Assert
    assert block.text == (
        "In order to achieve a significant improvement in road safety, "
        "the Government of India is committed to:"
    )


@pytest.mark.parametrize(
    ("title", "last_words"),
    [
        ("Preamble", "resulting from road accidents."),
        ("Raise Awareness about Road Safety Issues", "meaningful role in promoting road safety."),
        ("Safer Vehicles", "pedestrians and bicyclists) and infrastructure."),
    ],
)
def test_ends_each_block_where_the_next_heading_begins(
    blocks: list[Block], title: str, last_words: str
):
    # Arrange / Act
    block = only(blocks, f"{CITATION}, {title}")

    # Assert
    assert block.text.endswith(last_words)


@pytest.mark.parametrize(
    ("title", "joined_text"),
    [
        (
            "Road Traffic Safety Education and Training",
            "will encourage all professionals associated with road design, road construction",
        ),
        (
            "Implementation Strategy",
            "has also decided to establish a National Road Safety Fund to finance",
        ),
    ],
)
def test_joins_a_sentence_that_runs_across_a_page_break(
    blocks: list[Block], title: str, joined_text: str
):
    # Arrange / Act
    block = only(blocks, f"{CITATION}, {title}")

    # Assert
    assert joined_text in block.text


def test_ignores_a_second_copy_of_the_whole_document(pages: list[str], blocks: list[Block]):
    # Arrange / Act
    from_doubled_text = split_road_safety([*pages, *pages], ROAD_SAFETY_HEADINGS)

    # Assert
    assert from_doubled_text == blocks


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(cuts=st.sets(st.integers(min_value=1, max_value=120), max_size=8))
def test_cuts_the_same_blocks_wherever_the_pdf_breaks_its_pages(
    pages: list[str], blocks: list[Block], cuts: set[int]
):
    # Arrange
    lines = "\n".join(pages).split("\n")
    edges = [0, *sorted(cut for cut in cuts if cut < len(lines)), len(lines)]
    repaged = ["\n".join(lines[start:end]) for start, end in zip(edges, edges[1:], strict=False)]

    # Act
    result = split_road_safety(repaged, ROAD_SAFETY_HEADINGS)

    # Assert
    assert [replace(block, page=None) for block in result] == [
        replace(block, page=None) for block in blocks
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Preamble\nThe Government is concerned.\nPolicy Statements\nThe Government commits.",
        "National Road Safety Policy\nPreamble\nThe Government is concerned.\n"
        "Policy Statements\nThe Government commits.",
    ],
    ids=["text opens at the first heading", "only the document title precedes the first heading"],
)
def test_omits_the_introduction_when_no_opening_text_precedes_the_first_heading(text: str):
    # Arrange / Act
    labels = [block.label for block in split_road_safety([text], TWO_SECTIONS)]

    # Assert
    assert labels == [f"{CITATION}, Preamble", f"{CITATION}, Policy Statements"]


def test_keeps_the_first_opening_line_when_it_is_not_the_document_title():
    # Arrange
    text = "The Cabinet approved this note.\nPreamble\nThe Government is concerned."

    # Act
    introduction = split_road_safety([text], TWO_SECTIONS[:1])[0]

    # Assert
    assert introduction.text == "The Cabinet approved this note."
    assert introduction.page == 1


def test_drops_a_repeated_line_that_differs_only_in_case_and_spacing():
    # Arrange
    text = (
        "Preamble\nThe Government will act.\n"
        "Policy Statements\nTHE  GOVERNMENT will   act.\nA second sentence."
    )

    # Act
    preamble, statements = split_road_safety([text], TWO_SECTIONS)

    # Assert
    assert (preamble.text, statements.text) == ("The Government will act.", "A second sentence.")


def test_treats_a_sentence_that_begins_with_a_heading_title_as_body_text():
    # Arrange
    headings = (Heading("Preamble"), Heading("Safer Vehicles", SUBSECTION))
    text = (
        "Preamble\nSafer Vehicles are covered later.\n"
        "Safer Vehicles\nThe Government will act on vehicle safety."
    )

    # Act
    preamble, vehicles = split_road_safety([text], headings)

    # Assert
    assert preamble.text == "Safer Vehicles are covered later."
    assert vehicles.text == "The Government will act on vehicle safety."


def test_names_the_last_found_heading_when_a_later_heading_is_missing(pages: list[str]):
    # Arrange
    headings = (*ROAD_SAFETY_HEADINGS, Heading("Toll Policy"))

    # Act / Assert
    with pytest.raises(ContractError, match="'Toll Policy' after 'Implementation Strategy'"):
        split_road_safety(pages, headings)


def test_names_the_start_of_the_document_when_the_first_heading_is_missing(pages: list[str]):
    # Arrange
    headings = (Heading("Toll Policy"), *ROAD_SAFETY_HEADINGS)

    # Act / Assert
    with pytest.raises(ContractError, match="'Toll Policy' after 'the start of the document'"):
        split_road_safety(pages, headings)


def test_fails_when_headings_are_registered_out_of_reading_order(pages: list[str]):
    # Arrange
    headings = (Heading("Policy Statements"), Heading("Preamble"))

    # Act / Assert
    with pytest.raises(ContractError, match="'Preamble' after 'Policy Statements'"):
        split_road_safety(pages, headings)


@pytest.mark.parametrize("empty_pages", [[], [""]], ids=["no pages", "one blank page"])
def test_fails_with_a_contract_error_when_the_pdf_has_no_text(empty_pages: list[str]):
    # Arrange / Act / Assert
    with pytest.raises(ContractError, match="'Preamble'"):
        split_road_safety(empty_pages, TWO_SECTIONS)
