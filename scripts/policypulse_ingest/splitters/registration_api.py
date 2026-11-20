"""Split the Customer Registration API specification into citation blocks.

The spec belongs to another system and may arrive as markdown or as a PDF. Each section is one
block, labeled by its heading path, for example `Registration API, Fuzzy screening > Timeout`.

Markdown sections come from ATX headings (`#` to `####`) outside fenced code. A single top-level
heading that comes first is the document title and is left out of the path. Text before the first
section is labeled Overview. Markdown keeps its line structure so tables and code stay readable.

PDF sections come from numbered headings such as `2.1 Timeout`. The number depth gives the nesting.
Wrapped lines are joined.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..blocks import Block
from ..extract import join_wrapped_lines, normalize_text

DOC_ID = "registration_api"
CITATION_NAME = "Registration API"
OVERVIEW = "Overview"
PATH_SEPARATOR = " > "

_ATX_HEADING = re.compile(r"^(#{1,4})\s+(\S.*?)\s*#*\s*$")
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(\S.*)$")
_FENCE_MARKERS = ("```", "~~~")
_MAX_NUMBERED_TITLE_CHARACTERS = 100


@dataclass
class _Section:
    path: tuple[str, ...]
    lines: list[str] = field(default_factory=list)


HeadingParser = Callable[[str], tuple[int, str] | None]


def split_registration_api(pages: list[str]) -> list[Block]:
    """Split the spec, given as page texts (one page for a markdown file), into section blocks."""
    lines = [normalize_text(line).rstrip() for line in "\n".join(pages).split("\n")]
    tagged = _tag_fenced_code(lines)
    is_markdown = any(_markdown_heading(line) for line, fenced in tagged if not fenced)
    parse_heading = _markdown_heading if is_markdown else _numbered_heading
    sections = _collect_sections(tagged, parse_heading, skip_title=is_markdown)
    blocks: list[Block] = []
    for section in sections:
        text = _section_text(section, is_markdown)
        if not text:
            continue
        path = section.path or (OVERVIEW,)
        label = f"{CITATION_NAME}, {PATH_SEPARATOR.join(path)}"
        blocks.append(Block(DOC_ID, label, (CITATION_NAME, *path), text))
    return blocks


def _tag_fenced_code(lines: list[str]) -> list[tuple[str, bool]]:
    """Pair each line with whether it is a fence marker or sits inside a fenced block."""
    tagged: list[tuple[str, bool]] = []
    in_fence = False
    for line in lines:
        is_marker = line.lstrip().startswith(_FENCE_MARKERS)
        if is_marker:
            in_fence = not in_fence
        tagged.append((line, is_marker or in_fence))
    return tagged


def _markdown_heading(line: str) -> tuple[int, str] | None:
    match = _ATX_HEADING.match(line)
    return (len(match.group(1)), match.group(2)) if match else None


def _numbered_heading(line: str) -> tuple[int, str] | None:
    match = _NUMBERED_HEADING.match(line.strip())
    if match is None:
        return None
    title = match.group(2)
    if not title[0].isupper() or title.endswith(".") or len(title) > _MAX_NUMBERED_TITLE_CHARACTERS:
        return None
    return match.group(1).count(".") + 1, title


def _collect_sections(
    tagged: list[tuple[str, bool]], parse_heading: HeadingParser, skip_title: bool
) -> list[_Section]:
    headings = [None if fenced else parse_heading(line) for line, fenced in tagged]
    title_index = _document_title_index(headings) if skip_title else None
    sections = [_Section(path=())]
    stack: list[tuple[int, str]] = []
    for index, ((line, _), heading) in enumerate(zip(tagged, headings, strict=True)):
        if heading is None:
            sections[-1].lines.append(line)
            continue
        if index == title_index:
            continue
        depth, title = heading
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack.append((depth, title))
        sections.append(_Section(path=tuple(name for _, name in stack)))
    return sections


def _document_title_index(headings: list[tuple[int, str] | None]) -> int | None:
    """Index of a lone top-level heading that comes first, which names the document."""
    found = [(index, heading[0]) for index, heading in enumerate(headings) if heading]
    if not found:
        return None
    top_level = min(depth for _, depth in found)
    top_level_indexes = [index for index, depth in found if depth == top_level]
    first_index = found[0][0]
    return first_index if top_level_indexes == [first_index] else None


def _section_text(section: _Section, is_markdown: bool) -> str:
    raw = "\n".join(section.lines)
    return raw.strip() if is_markdown else join_wrapped_lines(raw)
