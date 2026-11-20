"""Citation blocks and their markdown rendering.

A block is the smallest unit a citation can point at. Rendering wraps each block in a breadcrumb
heading, a `Cite as:` line and an `End of` line, so any chunk the RAG engine cuts from the rendered
file still carries a label.
"""

import re
from dataclasses import dataclass, replace

# 350 words is about 470 tokens at the 1.33 tokens per word typical of English legal text. That is
# well under the 824-token stride between chunk starts (chunk size 1024 minus overlap 200), so every
# chunk contains at least one complete marker line.
MAX_BLOCK_WORDS = 350

BREADCRUMB_SEPARATOR = " > "
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])(\s+)")


@dataclass(frozen=True)
class Block:
    """One citation unit: a label the agent copies, its place in the document, and its text."""

    doc_id: str
    label: str
    breadcrumb: tuple[str, ...]
    text: str
    page: int | None = None

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError(f"Block in document {self.doc_id!r} has an empty label.")
        if not self.text.strip():
            raise ValueError(f"Block {self.label!r} in document {self.doc_id!r} has no text.")


def render_blocks(blocks: list[Block]) -> str:
    """Render blocks as markdown, splitting any block over MAX_BLOCK_WORDS into labeled parts."""
    rendered = [
        _render_block(part) for block in blocks for part in split_long_block(block, MAX_BLOCK_WORDS)
    ]
    return "\n\n".join(rendered) + "\n"


def split_long_block(block: Block, max_words: int = MAX_BLOCK_WORDS) -> list[Block]:
    """Split a block into parts of at most max_words words, breaking at sentence boundaries.

    A single sentence longer than max_words breaks at a word boundary. Every part keeps the label
    and breadcrumb of the original.
    """
    if len(block.text.split()) <= max_words:
        return [block]
    return [replace(block, text=text) for text in _pack_sentences(block.text, max_words)]


def _render_block(block: Block) -> str:
    heading = BREADCRUMB_SEPARATOR.join(block.breadcrumb)
    return (
        f"### {heading}\n"
        f"Cite as: {block.label}\n"
        f"\n"
        f"{block.text}\n"
        f"\n"
        f"End of {block.label}"
    )


def _pack_sentences(text: str, max_words: int) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    current_words = 0
    pieces = _SENTENCE_BOUNDARY.split(text)
    sentences = pieces[0::2]
    separators = pieces[1::2] + [""]
    for sentence, separator in zip(sentences, separators, strict=True):
        sentence_words = len(sentence.split())
        if sentence_words > max_words:
            if current:
                parts.append("".join(current).rstrip())
                current, current_words = [], 0
            parts.extend(_split_words(sentence, max_words))
            continue
        if current_words + sentence_words > max_words:
            parts.append("".join(current).rstrip())
            current, current_words = [], 0
        current.append(sentence + separator)
        current_words += sentence_words
    if current:
        parts.append("".join(current).rstrip())
    return parts


def _split_words(sentence: str, max_words: int) -> list[str]:
    words = sentence.split()
    return [" ".join(words[start : start + max_words]) for start in range(0, len(words), max_words)]
