"""Contract tests for the acceptance eval set and its criteria file.

The eval set is the executable spec for the agent, so these tests pin its shape before any agent
code reads it.
"""

import json
import re
from pathlib import Path

import pytest
from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.eval_set import EvalSet

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
EVALSET_PATH = EVAL_DIR / "policypulse_evalset.json"
CONFIG_PATH = EVAL_DIR / "test_config.json"

REFUSAL_SENTENCE = "The provided reference documents do not cover this topic."
SEARCH_TOOL = "search_policy_documents"

# (eval_id, question) in acceptance order. The question text is the user-provided wording.
ACCEPTANCE_QUESTIONS = [
    (
        "q01_exact_duplicate_status",
        "What status does the registration API return for an exact duplicate, "
        "and how is it detected?",
    ),
    (
        "q02_gemini_timeout_fallback",
        "What happens if Gemini times out during fuzzy duplicate screening?",
    ),
    ("q03_candidate_cap", "How many candidates go to Gemini per call, and why?"),
    (
        "q04_gdpr_breach_notification",
        "How quickly must a personal data breach be reported under GDPR?",
    ),
    ("q05_gdpr_max_fine", "What is the maximum GDPR fine?"),
    (
        "q06_hipaa_minimum_necessary",
        'What is the "minimum necessary" principle under HIPAA?',
    ),
    (
        "q07_hipaa_criminal_penalties",
        "What criminal penalties does HIPAA set for wrongful disclosure?",
    ),
    (
        "q08_ncsp_workforce_target",
        "What workforce target does India's National Cyber Security Policy 2013 set?",
    ),
    (
        "q09_ncsp_24x7_bodies",
        "Which 24x7 bodies does the cyber security policy set up?",
    ),
    (
        "q10_road_safety_approval",
        "When was the National Road Safety Policy approved, and on whose recommendation?",
    ),
    (
        "q11_road_safety_funding",
        "How will road safety activities be funded and overseen?",
    ),
    (
        "q12_cross_doc_data_limits",
        "Our registration API sends customer data to Gemini. "
        "What in these docs supports limiting what we send?",
    ),
    (
        "q13_out_of_scope_speed_limit",
        "What is the speed limit on Indian national highways?",
    ),
]


@pytest.fixture(scope="module")
def evalset_json() -> dict:
    return json.loads(EVALSET_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cases(evalset_json: dict) -> list[dict]:
    return evalset_json["eval_cases"]


def _tool_uses(case: dict) -> list[dict]:
    return case["conversation"][0]["intermediate_data"]["tool_uses"]


def _final_text(case: dict) -> str:
    return case["conversation"][0]["final_response"]["parts"][0]["text"]


def test_eval_set_validates_as_an_adk_eval_set():
    # Arrange
    raw = EVALSET_PATH.read_text(encoding="utf-8")

    # Act
    eval_set = EvalSet.model_validate_json(raw)

    # Assert
    assert eval_set.eval_set_id == "policypulse_evalset"
    assert len(eval_set.eval_cases) == 13


def test_holds_the_13_acceptance_cases_in_order(cases: list[dict]):
    # Arrange
    expected_ids = [eval_id for eval_id, _ in ACCEPTANCE_QUESTIONS]

    # Act
    actual_ids = [case["eval_id"] for case in cases]

    # Assert
    assert actual_ids == expected_ids
    assert all(re.fullmatch(r"[a-zA-Z0-9_]+", eval_id) for eval_id in actual_ids)


@pytest.mark.parametrize(("eval_id", "question"), ACCEPTANCE_QUESTIONS)
def test_each_case_asks_its_question_verbatim(cases: list[dict], eval_id: str, question: str):
    # Arrange
    case = next(case for case in cases if case["eval_id"] == eval_id)

    # Act
    asked = case["conversation"][0]["user_content"]["parts"][0]["text"]

    # Assert
    assert asked == question


def test_each_case_expects_the_retrieval_tool(cases: list[dict]):
    # Arrange
    expected_call_counts = {"q12_cross_doc_data_limits": 2}

    # Act
    call_counts = {case["eval_id"]: _tool_uses(case) for case in cases}

    # Assert
    for eval_id, tool_uses in call_counts.items():
        assert len(tool_uses) == expected_call_counts.get(eval_id, 1), eval_id
        assert {use["name"] for use in tool_uses} == {SEARCH_TOOL}, eval_id


def test_every_case_rubric_is_typed_for_the_final_response_judge(cases: list[dict]):
    # Arrange
    rubrics = [rubric for case in cases for rubric in case["rubrics"]]

    # Act
    rubric_types = {rubric["type"] for rubric in rubrics}

    # Assert
    assert rubrics
    assert rubric_types == {"FINAL_RESPONSE_QUALITY"}


def test_every_case_has_rubrics_with_unique_ids(cases: list[dict]):
    # Arrange
    rubric_ids = [rubric["rubric_id"] for case in cases for rubric in case["rubrics"]]

    # Act
    duplicates = {rubric_id for rubric_id in rubric_ids if rubric_ids.count(rubric_id) > 1}

    # Assert
    assert all(case["rubrics"] for case in cases)
    assert not duplicates


def test_the_q13_reference_is_the_refusal_sentence(cases: list[dict]):
    # Arrange
    q13 = next(case for case in cases if case["eval_id"] == "q13_out_of_scope_speed_limit")

    # Act
    reference = _final_text(q13)

    # Assert
    assert reference == REFUSAL_SENTENCE


def test_the_q12_reference_names_every_supporting_source(cases: list[dict]):
    # Arrange
    q12 = next(case for case in cases if case["eval_id"] == "q12_cross_doc_data_limits")

    # Act
    reference = _final_text(q12)

    # Assert
    for citation in (
        "[Registration API]",
        "[GDPR Art. 5(1)(c)]",
        "[HIPAA Privacy Rule Summary]",
        "[NCSP 2013, Objective 10]",
    ):
        assert citation in reference


def test_test_config_sets_the_agreed_criteria():
    # Arrange
    raw = CONFIG_PATH.read_text(encoding="utf-8")

    # Act
    config = EvalConfig.model_validate_json(raw)
    criteria = json.loads(raw)["criteria"]

    # Assert
    assert {
        "tool_trajectory_avg_score",
        "rubric_based_final_response_quality_v1",
        "hallucinations_v1",
        "response_match_score",
    } <= set(config.criteria)
    trajectory = criteria["tool_trajectory_avg_score"]
    assert trajectory["match_type"] == "IN_ORDER"
    assert trajectory["ignore_args"] is True
    assert trajectory["threshold"] == 1.0
