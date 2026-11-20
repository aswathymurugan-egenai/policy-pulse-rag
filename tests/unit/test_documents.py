from pathlib import Path

import pytest

from policypulse_ingest.blocks import Block
from policypulse_ingest.documents import (
    DOCUMENTS,
    check_contract,
    document_by_id,
    resolve_sources,
)
from policypulse_ingest.errors import ContractError, UsageError


def block(doc_id: str, label: str) -> Block:
    return Block(doc_id, label, ("breadcrumb",), "Some text.")


def touch_all_sources(docs_dir: Path) -> None:
    for document in DOCUMENTS:
        (docs_dir / document.file_names[0]).write_bytes(b"x")


def test_registry_lists_five_documents_with_distinct_ids_and_citation_names():
    # Arrange / Act
    ids = [document.doc_id for document in DOCUMENTS]
    names = [document.citation_name for document in DOCUMENTS]

    # Assert
    assert len(DOCUMENTS) == 5
    assert len(set(ids)) == 5
    assert len(set(names)) == 5
    assert set(names) == {
        "GDPR",
        "HIPAA Privacy Rule Summary",
        "NCSP 2013",
        "Road Safety Policy",
        "Registration API",
    }


def test_reports_every_missing_source_file(tmp_path: Path):
    # Arrange / Act
    with pytest.raises(UsageError) as error:
        resolve_sources(tmp_path)

    # Assert
    message = str(error.value)
    for expected in (
        "gdpr_regulation_2016_679.pdf",
        "privacysummary.pdf",
        "national_cyber_security_policy_2013.pdf",
        "national_road_safety_policy_2010.pdf",
        "customer_registration_api_spec.md",
    ):
        assert expected in message


def test_resolves_every_source_when_all_are_present(tmp_path: Path):
    # Arrange
    touch_all_sources(tmp_path)

    # Act
    sources = resolve_sources(tmp_path)

    # Assert
    assert set(sources) == {document.doc_id for document in DOCUMENTS}
    assert sources["gdpr"] == tmp_path / "gdpr_regulation_2016_679.pdf"


@pytest.mark.parametrize("suffix", [".md", ".pdf"])
def test_accepts_the_api_spec_as_markdown_or_pdf(tmp_path: Path, suffix: str):
    # Arrange
    touch_all_sources(tmp_path)
    (tmp_path / "customer_registration_api_spec.md").unlink(missing_ok=True)
    spec = tmp_path / f"customer_registration_api_spec{suffix}"
    spec.write_bytes(b"x")

    # Act
    sources = resolve_sources(tmp_path)

    # Assert
    assert sources["registration_api"] == spec


def test_rejects_the_api_spec_supplied_in_both_formats(tmp_path: Path):
    # Arrange
    touch_all_sources(tmp_path)
    (tmp_path / "customer_registration_api_spec.md").write_bytes(b"x")
    (tmp_path / "customer_registration_api_spec.pdf").write_bytes(b"x")

    # Act / Assert
    with pytest.raises(UsageError, match="customer_registration_api_spec"):
        resolve_sources(tmp_path)


def test_contract_gate_fails_when_a_required_label_is_missing():
    # Arrange
    gdpr = document_by_id("gdpr")
    blocks = gdpr_blocks(padded_to_count=gdpr.block_count_range[0], omit="Art. 33")

    # Act / Assert
    with pytest.raises(ContractError, match=r"GDPR Art\. 33"):
        check_contract(gdpr, blocks)


def test_contract_gate_accepts_a_document_that_meets_its_contract():
    # Arrange
    gdpr = document_by_id("gdpr")
    blocks = gdpr_blocks(padded_to_count=gdpr.block_count_range[0])

    # Act / Assert
    check_contract(gdpr, blocks)


def test_contract_gate_fails_when_a_label_breaks_the_documents_label_pattern():
    # Arrange
    gdpr = document_by_id("gdpr")
    blocks = gdpr_blocks(padded_to_count=gdpr.block_count_range[0])
    blocks.append(block("gdpr", "GDPR Article thirty-three"))

    # Act / Assert
    with pytest.raises(ContractError, match="Article thirty-three"):
        check_contract(gdpr, blocks)


def test_contract_gate_fails_when_the_block_count_is_outside_the_expected_range():
    # Arrange
    gdpr = document_by_id("gdpr")
    blocks = gdpr_blocks(padded_to_count=0)

    # Act / Assert
    assert len(blocks) < gdpr.block_count_range[0]
    with pytest.raises(ContractError, match=r"\d+ blocks"):
        check_contract(gdpr, blocks)


def gdpr_blocks(padded_to_count: int, omit: str = "\0") -> list[Block]:
    """Blocks carrying every required GDPR label, padded with extra paragraph labels."""
    labels = [label for label in document_by_id("gdpr").required_labels if omit not in label]
    blocks = [block("gdpr", label) for label in labels]
    paragraph = 2
    while len(blocks) < padded_to_count:
        blocks.append(block("gdpr", f"GDPR Art. 1({paragraph})"))
        paragraph += 1
    return blocks
