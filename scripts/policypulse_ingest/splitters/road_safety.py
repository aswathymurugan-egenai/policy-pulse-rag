"""Split the National Road Safety Policy (India, 2010) into citation blocks.

The document is four pages of unnumbered, titled sections: an opening note, Preamble, Policy
Statements, one heading per policy statement, and Implementation Strategy. The registry lists the
headings in reading order and each becomes a block. The opening note before the Preamble is the
Introduction block. A heading missing from the text raises a ContractError.

The PDF text has layout echoes: one heading and its first lines appear a second time, with the tail
of that sentence landing after a later section. A line that repeats an earlier line, ignoring case
and spacing, is dropped, which removes the echo and leaves the first complete copy.
"""

from dataclasses import dataclass

from ..blocks import Block
from ..errors import ContractError
from ..extract import join_wrapped_lines, normalize_text
from .headings import SECTION, SUBSECTION, Heading

DOC_ID = "road_safety"
CITATION_NAME = "Road Safety Policy"
INTRODUCTION_LABEL = f"{CITATION_NAME}, Introduction"

_DOCUMENT_TITLE = "National Road Safety Policy"
_POLICY_STATEMENTS = "Policy Statements"
_MAX_HEADING_LINES = 3

ROAD_SAFETY_HEADINGS: tuple[Heading, ...] = (
    Heading("Preamble"),
    Heading(_POLICY_STATEMENTS),
    Heading("Raise Awareness about Road Safety Issues", SUBSECTION),
    Heading("Establish a Road Safety Information Database", SUBSECTION),
    Heading("Ensure Safer Road Infrastructure", SUBSECTION),
    Heading("Safer Vehicles", SUBSECTION),
    Heading("Safer Drivers", SUBSECTION),
    Heading("Safety of Vulnerable Road Users", SUBSECTION),
    Heading("Road Traffic Safety Education and Training", SUBSECTION),
    Heading("Enforcement of Safety Laws", SUBSECTION),
    Heading("Emergency Medical Services for Road Accidents", SUBSECTION),
    Heading("HRD & Research for Road Safety", SUBSECTION),
    Heading(
        "Strengthening Enabling Legal, Institutional and Financial Environment for Road Safety",
        SUBSECTION,
    ),
    Heading("Implementation Strategy"),
)


@dataclass(frozen=True)
class _Line:
    page: int
    text: str


@dataclass(frozen=True)
class _Hit:
    heading: Heading
    first_line: int
    body_start: int


def split_road_safety(
    pages: list[str], headings: tuple[Heading, ...] = ROAD_SAFETY_HEADINGS
) -> list[Block]:
    """Split the page texts of the Road Safety Policy PDF at the given headings."""
    lines = _lines(pages)
    hits = _locate_headings(lines, headings)
    blocks = _introduction(lines, hits[0].first_line)
    section = ""
    for position, hit in enumerate(hits):
        if hit.heading.level == SECTION:
            section = hit.heading.title
        end = hits[position + 1].first_line if position + 1 < len(hits) else len(lines)
        blocks.append(_build_block(lines, hit, end, section))
    return blocks


def _lines(pages: list[str]) -> list[_Line]:
    lines: list[_Line] = []
    seen: set[str] = set()
    for page_number, page in enumerate(pages, start=1):
        for raw_line in normalize_text(page).split("\n"):
            text = raw_line.strip()
            key = " ".join(text.lower().split())
            if not text or key in seen:
                continue
            seen.add(key)
            lines.append(_Line(page_number, text))
    return lines


def _locate_headings(lines: list[_Line], headings: tuple[Heading, ...]) -> list[_Hit]:
    hits: list[_Hit] = []
    cursor = 0
    previous = "the start of the document"
    for heading in headings:
        hit = _find_heading(lines, heading, cursor)
        if hit is None:
            raise ContractError(
                f"The Road Safety Policy text has no heading {heading.title!r} after {previous!r}. "
                "Check that docs/ holds the policy PDF, or update ROAD_SAFETY_HEADINGS."
            )
        hits.append(hit)
        cursor = hit.body_start
        previous = heading.title
    return hits


def _find_heading(lines: list[_Line], heading: Heading, cursor: int) -> _Hit | None:
    for index in range(cursor, len(lines)):
        parts: list[str] = []
        for offset in range(_MAX_HEADING_LINES):
            if index + offset >= len(lines):
                break
            parts.append(lines[index + offset].text)
            if " ".join(" ".join(parts).split()) == heading.title:
                return _Hit(heading, index, index + offset + 1)
    return None


def _introduction(lines: list[_Line], first_heading_line: int) -> list[Block]:
    body = [line.text for line in lines[:first_heading_line]]
    if body and body[0] == _DOCUMENT_TITLE:
        body = body[1:]
    text = join_wrapped_lines("\n".join(body))
    if not text:
        return []
    return [Block(DOC_ID, INTRODUCTION_LABEL, (CITATION_NAME, "Introduction"), text, page=1)]


def _build_block(lines: list[_Line], hit: _Hit, end: int, section: str) -> Block:
    body = [line.text for line in lines[hit.body_start : end]]
    if body and body[0].startswith(hit.heading.title + " "):
        body[0] = body[0][len(hit.heading.title) :].strip()
    text = join_wrapped_lines("\n".join(body))
    title = hit.heading.title
    if hit.heading.level == SECTION:
        breadcrumb = (CITATION_NAME, title)
    else:
        breadcrumb = (CITATION_NAME, section, title)
    page = lines[hit.first_line].page
    return Block(DOC_ID, f"{CITATION_NAME}, {title}", breadcrumb, text, page)
