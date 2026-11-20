import re

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from policypulse_ingest.blocks import MAX_BLOCK_WORDS, Block, render_blocks, split_long_block

WINDOW_WORDS = 600


def make_block(text: str, label: str = "GDPR Art. 33(1)") -> Block:
    return Block(
        doc_id="gdpr",
        label=label,
        breadcrumb=("GDPR", "Article 33 Notification of a personal data breach", "Paragraph 1"),
        text=text,
        page=None,
    )


def sentences(count: int, words_per_sentence: int) -> str:
    sentence = " ".join(["word"] * (words_per_sentence - 1)) + " end."
    return " ".join(f"{sentence}" for _ in range(count))


def test_renders_heading_cite_line_body_and_end_line():
    # Arrange
    block = make_block("The controller shall notify the supervisory authority.")

    # Act
    rendered = render_blocks([block])

    # Assert
    assert rendered == (
        "### GDPR > Article 33 Notification of a personal data breach > Paragraph 1\n"
        "Cite as: GDPR Art. 33(1)\n"
        "\n"
        "The controller shall notify the supervisory authority.\n"
        "\n"
        "End of GDPR Art. 33(1)\n"
    )


def test_separates_blocks_with_one_blank_line():
    # Arrange
    blocks = [make_block("First.", "GDPR Art. 1(1)"), make_block("Second.", "GDPR Art. 1(2)")]

    # Act
    rendered = render_blocks(blocks)

    # Assert
    assert "End of GDPR Art. 1(1)\n\n### GDPR" in rendered
    assert rendered.endswith("End of GDPR Art. 1(2)\n")


def test_splits_a_block_over_350_words_at_sentence_boundaries():
    # Arrange
    block = make_block(sentences(count=40, words_per_sentence=20))

    # Act
    parts = split_long_block(block)

    # Assert
    assert len(parts) > 1
    for part in parts:
        assert len(part.text.split()) <= MAX_BLOCK_WORDS
        assert part.text.endswith("end.")
        assert part.label == block.label
        assert part.breadcrumb == block.breadcrumb
    assert " ".join(part.text for part in parts) == block.text


def test_keeps_a_short_block_whole():
    # Arrange
    block = make_block(sentences(count=3, words_per_sentence=20))

    # Act
    parts = split_long_block(block)

    # Assert
    assert parts == [block]


def test_splits_a_single_oversized_sentence_at_word_boundaries():
    # Arrange
    block = make_block(" ".join(["word"] * 900))

    # Act
    parts = split_long_block(block)

    # Assert
    assert all(len(part.text.split()) <= MAX_BLOCK_WORDS for part in parts)
    assert sum(len(part.text.split()) for part in parts) == 900


def test_repeats_the_labels_on_every_part_of_a_split_block():
    # Arrange
    block = make_block(sentences(count=40, words_per_sentence=20))

    # Act
    rendered = render_blocks([block])

    # Assert
    part_count = len(split_long_block(block))
    assert rendered.count("Cite as: GDPR Art. 33(1)") == part_count
    assert rendered.count("End of GDPR Art. 33(1)") == part_count


@pytest.mark.parametrize("label", ["", "   "])
def test_rejects_a_block_with_an_empty_label(label: str):
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="label"):
        make_block("Some text.", label=label)


def has_marker_in_every_window(rendered: str) -> bool:
    """True when every WINDOW_WORDS-word window holds a `Cite as:` or `End of` line."""
    marker_word_indexes: list[int] = []
    word_count = 0
    for line in rendered.splitlines():
        if re.match(r"(Cite as:|End of) ", line):
            marker_word_indexes.append(word_count)
        word_count += len(line.split())
    last_window_start = word_count - WINDOW_WORDS
    for start in range(max(last_window_start, 0) + 1):
        window_end = start + WINDOW_WORDS
        if not any(start <= index < window_end for index in marker_word_indexes):
            return False
    return True


WORDS = st.sampled_from(["alpha", "beta.", "gamma", "delta;", "epsilon.", "zeta", "eta,", "theta."])
BLOCK_TEXTS = st.lists(WORDS, min_size=1, max_size=1500).map(" ".join)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(texts=st.lists(BLOCK_TEXTS, min_size=1, max_size=3))
def test_every_600_word_window_carries_a_label_marker(texts: list[str]):
    # Arrange
    blocks = [make_block(text, label=f"GDPR Art. {index}(1)") for index, text in enumerate(texts)]

    # Act
    rendered = render_blocks(blocks)

    # Assert
    assert has_marker_in_every_window(rendered)
