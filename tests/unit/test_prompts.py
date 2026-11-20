import json
import re
from pathlib import Path

from policypulse_ingest.documents import DOCUMENTS
from policypulse_rag.prompts import CITATION_NAMES, INSTRUCTION, REFUSAL_SENTENCE

EVALSET_PATH = Path(__file__).resolve().parents[2] / "eval" / "policypulse_evalset.json"


def rule(number: int) -> str:
    """The text of one numbered rule, from its heading to the next blank line."""
    match = re.search(rf"RULE {number}\.[^\n]*\n(.*?)(?:\n\n|\Z)", INSTRUCTION, flags=re.DOTALL)
    assert match, f"RULE {number} is missing from the instruction"
    return match.group(0)


def example_labels() -> list[str]:
    """Labels written in square brackets in the citation rule."""
    return re.findall(r"\[([^\[\]]+)\]", rule(2))


def test_requires_a_search_before_every_answer():
    # Arrange / Act
    text = rule(1)

    # Assert
    assert "SEARCH BEFORE EVERY ANSWER" in text
    assert "search_policy_documents at least once for every user message" in text
    assert "Never answer from memory or general knowledge" in text


def test_shows_an_example_label_for_each_document_matching_its_label_pattern():
    # Arrange
    labels = example_labels()

    # Act
    documents_with_example = {
        document.doc_id
        for document in DOCUMENTS
        if any(document.label_pattern.match(label) for label in labels)
    }

    # Assert
    assert documents_with_example == {document.doc_id for document in DOCUMENTS}


def test_every_example_label_matches_some_documents_label_pattern():
    # Arrange
    labels = example_labels()

    # Act
    unmatched = [
        label
        for label in labels
        if not any(document.label_pattern.match(label) for document in DOCUMENTS)
    ]

    # Assert
    assert labels
    assert unmatched == []


def test_contains_the_refusal_sentence_verbatim_and_it_equals_the_eval_sets_q13_reference():
    # Arrange
    evalset = json.loads(EVALSET_PATH.read_text(encoding="utf-8"))
    q13 = next(case for case in evalset["eval_cases"] if case["eval_id"].startswith("q13"))
    reference = q13["conversation"][0]["final_response"]["parts"][0]["text"]

    # Act / Assert
    assert REFUSAL_SENTENCE == "The provided reference documents do not cover this topic."
    assert REFUSAL_SENTENCE == reference
    assert f"\n{REFUSAL_SENTENCE}\n" in INSTRUCTION


def test_instructs_one_search_per_document_for_cross_document_questions():
    # Arrange / Act
    text = rule(3)

    # Assert
    assert "call search_policy_documents once for each document involved" in text
    assert "names the document and the topic" in text


def test_separates_hipaa_minimum_necessary_from_gdpr_data_minimisation():
    # Arrange / Act
    text = rule(5)

    # Assert
    assert "Never attribute a HIPAA rule to GDPR or a GDPR rule to HIPAA" in text
    assert '"Minimum necessary" is the HIPAA standard' in text
    assert '"Data minimisation" is the GDPR principle in Art. 5(1)(c)' in text


def test_names_every_source_document_by_its_citation_name():
    # Arrange
    registry_names = {document.citation_name for document in DOCUMENTS}

    # Act / Assert
    assert set(CITATION_NAMES) == registry_names
    assert all(name in INSTRUCTION for name in CITATION_NAMES)


def test_contains_no_curly_braces_because_adk_reads_them_as_state_placeholders():
    # Arrange / Act / Assert
    assert "{" not in INSTRUCTION
    assert "}" not in INSTRUCTION
