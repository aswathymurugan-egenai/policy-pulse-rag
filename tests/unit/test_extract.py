import re

from policypulse_ingest.extract import join_wrapped_lines, normalize_text, strip_lines


def test_joins_wrapped_lines_inside_a_paragraph():
    # Arrange
    text = "alpha beta\ngamma delta\n\nepsilon\nzeta"

    # Act
    joined = join_wrapped_lines(text)

    # Assert
    assert joined == "alpha beta gamma delta\nepsilon zeta"


def test_removes_a_soft_hyphen_at_a_line_end_and_joins_the_word():
    # Arrange
    text = "measures of pseudonymi­\nsation apply"

    # Act
    joined = join_wrapped_lines(text)

    # Assert
    assert joined == "measures of pseudonymisation apply"


def test_keeps_a_real_hyphen_at_a_line_end_because_it_joins_a_compound():
    # Arrange
    text = "a non-\nworkforce member and E-\nGovernance services"

    # Act
    joined = join_wrapped_lines(text)

    # Assert
    assert joined == "a non-workforce member and E-Governance services"


def test_removes_soft_hyphens_inside_a_line():
    # Arrange / Act
    joined = join_wrapped_lines("tech­nical measures")

    # Assert
    assert joined == "technical measures"


def test_starts_a_new_paragraph_at_each_bullet():
    # Arrange
    text = "Intro line\n• first item\nstill first\n• second item"

    # Act
    joined = join_wrapped_lines(text)

    # Assert
    assert joined == "Intro line\n• first item still first\n• second item"


def test_collapses_runs_of_spaces():
    # Arrange / Act
    joined = join_wrapped_lines("(1)   The  protection    of persons")

    # Assert
    assert joined == "(1) The protection of persons"


def test_strips_lines_matching_the_documents_header_patterns():
    # Arrange
    text = "Page 2 of 9\nbody line one\nPage 3 of 9\nbody line two"

    # Act
    stripped = strip_lines(text, [re.compile(r"^\s*Page \d+ of \d+\s*$")])

    # Assert
    assert stripped == "body line one\nbody line two"


def test_leaves_body_lines_untouched_when_no_pattern_matches():
    # Arrange
    text = "first\nsecond"

    # Act
    stripped = strip_lines(text, [re.compile(r"^Page ")])

    # Assert
    assert stripped == text


def test_normalizes_private_use_bullets_and_no_break_spaces():
    # Arrange
    text = " The Government of India"

    # Act
    normalized = normalize_text(text)

    # Assert
    assert normalized == "• The Government of India"
