"""Text extraction and cleanup shared by the per-document splitters.

`read_pdf_pages` is the one pypdf boundary. The other functions are pure text transforms.
"""

import logging
import re
from collections.abc import Iterable
from pathlib import Path

from pypdf import PdfReader

BULLET = "•"
SOFT_HYPHEN = "­"
_PRIVATE_USE_BULLET = ""
_SPACE_VARIANTS = (" ", " ", " ")
_RUN_OF_SPACES = re.compile(r"[ \t]+")
_HYPHEN_AFTER_WORD_CHARACTER = re.compile(r"\w-$")


def read_pdf_pages(path: Path) -> list[str]:
    """Return the extracted text of each PDF page, in order. Page 1 is index 0."""
    # pypdf logs one warning per font when fontTools is absent; the text still extracts.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(str(path))
    return [page.extract_text() or "" for page in reader.pages]


def normalize_text(text: str) -> str:
    """Map private-use bullet glyphs to a bullet and no-break spaces to plain spaces."""
    text = text.replace(_PRIVATE_USE_BULLET, BULLET)
    for variant in _SPACE_VARIANTS:
        text = text.replace(variant, " ")
    return text


def strip_lines(text: str, patterns: Iterable[re.Pattern[str]]) -> str:
    """Remove every line that matches any of the patterns. Other lines are left as they are."""
    compiled = list(patterns)
    kept = [line for line in text.split("\n") if not any(p.search(line) for p in compiled)]
    return "\n".join(kept)


def join_wrapped_lines(text: str) -> str:
    """Join physical lines into one line per paragraph.

    A blank line or a bullet starts a new paragraph. A soft hyphen at a line end marks a word the
    PDF broke by hyphenation, so it is removed and the halves are joined. An ordinary hyphen at a
    line end belongs to a compound such as "non-workforce", so it stays and the halves are joined.
    """
    paragraphs: list[str] = []
    current = ""
    for raw_line in text.split("\n"):
        line = _RUN_OF_SPACES.sub(" ", raw_line).strip()
        if not line:
            current = _flush(paragraphs, current)
            continue
        if line.startswith(BULLET):
            current = _flush(paragraphs, current)
        current = _append_line(current, line)
    _flush(paragraphs, current)
    return "\n".join(paragraph.replace(SOFT_HYPHEN, "") for paragraph in paragraphs)


def _flush(paragraphs: list[str], current: str) -> str:
    if current:
        paragraphs.append(current)
    return ""


def _append_line(current: str, line: str) -> str:
    if not current:
        return line
    if current.endswith(SOFT_HYPHEN):
        return current[:-1] + line
    if _HYPHEN_AFTER_WORD_CHARACTER.search(current):
        return current + line
    return f"{current} {line}"
