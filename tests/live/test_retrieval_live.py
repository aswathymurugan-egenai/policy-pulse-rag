"""Retrieval recall against the live corpus. Run manually: pytest -m live tests/live -s

Each case sends a query to RAG Engine with the agent's store settings and asserts that every
expected citation label appears in the top 10 chunks. Distances are printed so the distance
threshold is only changed against recorded numbers.
"""

from collections.abc import Callable
from typing import Any

import pytest

pytestmark = pytest.mark.live

# (case id, query, labels that must each appear in some chunk). A label ending in a comma or a
# partial name matches any block of that unit.
RECALL_CASES = [
    (
        "q01_exact_duplicate_status",
        "registration API exact duplicate status code and detection",
        ["Registration API, "],
    ),
    (
        "q02_gemini_timeout_fallback",
        "fuzzy duplicate screening Gemini timeout fallback",
        ["Registration API, "],
    ),
    (
        "q03_candidate_cap",
        "maximum candidates sent to Gemini per fuzzy screening call",
        ["Registration API, "],
    ),
    (
        "q04_gdpr_breach_notification",
        "GDPR personal data breach notification deadline to the supervisory authority",
        ["GDPR Art. 33(1)"],
    ),
    ("q05_gdpr_max_fine", "GDPR maximum administrative fine", ["GDPR Art. 83(5)"]),
    (
        "q06_hipaa_minimum_necessary",
        "HIPAA minimum necessary use and disclosure standard",
        ["HIPAA Privacy Rule Summary, Minimum Necessary"],
    ),
    (
        "q07_hipaa_criminal_penalties",
        "HIPAA criminal penalties for wrongful disclosure",
        ["HIPAA Privacy Rule Summary, Criminal Penalties"],
    ),
    (
        "q08_ncsp_workforce_target",
        "NCSP 2013 workforce target cyber security professionals",
        ["NCSP 2013, Objective 8"],
    ),
    (
        "q09_ncsp_24x7_bodies",
        "NCSP 2013 24x7 CERT-In sectoral CERTs NCIIPC",
        ["NCSP 2013, Strategy E", "NCSP 2013, Strategy G"],
    ),
    (
        "q10_road_safety_approval",
        "National Road Safety Policy approval date and committee recommendation",
        ["Road Safety Policy, Introduction"],
    ),
    (
        "q11_road_safety_funding",
        "National Road Safety Fund and Board funding and oversight",
        ["Road Safety Policy, Implementation Strategy"],
    ),
    (
        "q12_registration_api_data_limits",
        "Registration API candidate cap and minimized screening profile sent to Gemini",
        ["Registration API, "],
    ),
    (
        "q12_gdpr_data_minimisation",
        "GDPR data minimisation adequate relevant and limited to what is necessary",
        ["GDPR Art. 5(1)(c)"],
    ),
    (
        "q12_hipaa_minimum_necessary",
        "HIPAA minimum necessary standard for protected health information",
        ["HIPAA Privacy Rule Summary, Minimum Necessary"],
    ),
    (
        "q12_ncsp_data_in_transit",
        "NCSP 2013 protecting information in process, handling, storage and transit",
        ["NCSP 2013, Objective 10"],
    ),
]

OUT_OF_SCOPE_QUERY = "speed limit on Indian national highways"


def carries_label(context: Any, label: str) -> bool:
    text = context.text or ""
    return f"Cite as: {label}" in text or f"End of {label}" in text


@pytest.mark.parametrize(
    ("case_id", "query", "expected_labels"), RECALL_CASES, ids=[case[0] for case in RECALL_CASES]
)
def test_expected_label_is_in_the_top_10(
    retrieve: Callable[[str], list[Any]],
    case_id: str,
    query: str,
    expected_labels: list[str],
):
    # Arrange / Act
    contexts = retrieve(query)

    # Assert
    for label in expected_labels:
        ranks = [
            (rank, context.distance)
            for rank, context in enumerate(contexts, start=1)
            if carries_label(context, label)
        ]
        found = f"{label!r} found at (rank, distance) {ranks[:3]}"
        print(f"{case_id}: {found} of {len(contexts)} chunks")
        assert ranks, f"{label!r} is not in the {len(contexts)} chunks retrieved for {query!r}"


def test_records_the_best_distance_for_the_out_of_scope_question(
    retrieve: Callable[[str], list[Any]],
):
    # Arrange / Act
    contexts = retrieve(OUT_OF_SCOPE_QUERY)

    # Assert
    distances = [context.distance for context in contexts if context.distance is not None]
    best = min(distances) if distances else None
    print(f"q13_out_of_scope_speed_limit: best distance {best} across {len(contexts)} chunks")
