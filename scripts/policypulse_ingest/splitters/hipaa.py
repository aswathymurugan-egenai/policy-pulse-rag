"""Split the HHS Summary of the HIPAA Privacy Rule into citation blocks.

The summary has section headings set in a left-hand column (the PDF text wraps them over several
short lines) and run-in subsection headings that open a paragraph, such as "Minimum Necessary.  A
central aspect ...". The registry lists both kinds in reading order. A heading missing from the text
raises a ContractError, because every block after it would carry the wrong label.

The label carries the PDF page the heading is on, counted from 1. The End Notes are not cited.
"""

import re
from dataclasses import dataclass

from ..blocks import Block
from ..errors import ContractError
from ..extract import join_wrapped_lines, normalize_text, strip_lines
from .headings import SECTION, SUBSECTION, Heading

DOC_ID = "hipaa"
CITATION_NAME = "HIPAA Privacy Rule Summary"

_NOISE = [re.compile(r"^\s*OCR Privacy Rule Summary\s+\d+\s+Last Revised\s+\d+/\d+\s*$")]
_MAX_HEADING_LINES = 6

HIPAA_HEADINGS: tuple[Heading, ...] = (
    Heading("Introduction"),
    Heading("Statutory & Regulatory Background"),
    Heading("Who is Covered by the Privacy Rule"),
    Heading("Health Plans", SUBSECTION),
    Heading("Health Care Providers", SUBSECTION),
    Heading("Health Care Clearinghouses", SUBSECTION),
    Heading("Business Associates"),
    Heading("Business Associate Defined", SUBSECTION),
    Heading("Business Associate Contract", SUBSECTION),
    Heading("What Information is Protected"),
    Heading("Protected Health Information", SUBSECTION),
    Heading("De-Identified Health Information", SUBSECTION),
    Heading("General Principle for Uses and Disclosures"),
    Heading("Basic Principle", SUBSECTION),
    Heading("Required Disclosures", SUBSECTION),
    Heading("Permitted Uses and Disclosures"),
    Heading("Permitted Uses and Disclosures", SUBSECTION),
    Heading("To the Individual", SUBSECTION),
    Heading("Treatment, Payment, Health Care Operations", SUBSECTION),
    Heading("Uses and Disclosures with Opportunity to Agree or Object", SUBSECTION),
    Heading("Facility Directories", SUBSECTION),
    Heading("For Notification and Other Purposes", SUBSECTION),
    Heading("Incidental Use and Disclosure", SUBSECTION),
    Heading("Public Interest and Benefit Activities", SUBSECTION),
    Heading("Required by Law", SUBSECTION),
    Heading("Public Health Activities", SUBSECTION),
    Heading("Victims of Abuse, Neglect or Domestic Violence", SUBSECTION),
    Heading("Health Oversight Activities", SUBSECTION),
    Heading("Judicial and Administrative Proceedings", SUBSECTION),
    Heading("Law Enforcement Purposes", SUBSECTION),
    Heading("Decedents", SUBSECTION),
    Heading("Cadaveric Organ, Eye, or Tissue Donation", SUBSECTION),
    Heading("Research", SUBSECTION),
    Heading("Serious Threat to Health or Safety", SUBSECTION),
    Heading("Essential Government Functions", SUBSECTION),
    Heading("Workers’ Compensation", SUBSECTION),
    Heading("Limited Data Set", SUBSECTION),
    Heading("Authorized Uses and Disclosures"),
    Heading("Authorization", SUBSECTION),
    Heading("Psychotherapy Notes", SUBSECTION),
    Heading("Marketing", SUBSECTION),
    Heading("Limiting Uses and Disclosures to the Minimum Necessary"),
    Heading("Minimum Necessary", SUBSECTION),
    Heading("Access and Uses", SUBSECTION),
    Heading("Disclosures and Requests for Disclosures", SUBSECTION),
    Heading("Reasonable Reliance", SUBSECTION),
    Heading("Notice and Other Individual Rights"),
    Heading("Privacy Practices Notice", SUBSECTION),
    Heading("Access", SUBSECTION),
    Heading("Amendment", SUBSECTION),
    Heading("Disclosure Accounting", SUBSECTION),
    Heading("Restriction Request", SUBSECTION),
    Heading("Confidential Communications Requirements", SUBSECTION),
    Heading("Administrative Requirements"),
    Heading("Privacy Policies and Procedures", SUBSECTION),
    Heading("Privacy Personnel", SUBSECTION),
    Heading("Workforce Training and Management", SUBSECTION),
    Heading("Mitigation", SUBSECTION),
    Heading("Data Safeguards", SUBSECTION),
    Heading("Complaints", SUBSECTION),
    Heading("Retaliation and Waiver", SUBSECTION),
    Heading("Documentation and Record Retention", SUBSECTION),
    Heading("Fully-Insured Group Health Plan Exception", SUBSECTION),
    Heading("Organizational Options"),
    Heading("Hybrid Entity", SUBSECTION),
    Heading("Affiliated Covered Entity", SUBSECTION),
    Heading("Organized Health Care Arrangement", SUBSECTION),
    Heading("Covered Entities With Multiple Covered Functions", SUBSECTION),
    Heading("Group Health Plan disclosures to Plan Sponsors", SUBSECTION),
    Heading("Other Provisions: Personal Representatives and Minors"),
    Heading("Personal Representatives", SUBSECTION),
    Heading("Special case: Minors", SUBSECTION),
    Heading("State Law"),
    Heading("Preemption", SUBSECTION),
    Heading("Exception Determination", SUBSECTION),
    Heading("Enforcement and Penalties for Noncompliance"),
    Heading("Compliance", SUBSECTION),
    Heading("Civil Money Penalties", SUBSECTION),
    Heading("Criminal Penalties", SUBSECTION),
    Heading("Compliance Dates"),
    Heading("Compliance Schedule", SUBSECTION),
    Heading("Small Health Plans", SUBSECTION),
    Heading("Copies of the Rule & Related Materials"),
    Heading("End Notes", keep=False),
)


@dataclass(frozen=True)
class _Line:
    page: int
    text: str
    starts_paragraph: bool


@dataclass(frozen=True)
class _Hit:
    """Where a heading sits in the line stream and what follows it on its own line."""

    heading: Heading
    first_line: int
    body_start: int
    remainder: str


def split_hipaa(pages: list[str], headings: tuple[Heading, ...] = HIPAA_HEADINGS) -> list[Block]:
    """Split the page texts of the HIPAA summary at the given headings, in reading order."""
    lines = _lines(pages)
    hits = _locate_headings(lines, headings)
    blocks: list[Block] = []
    section = ""
    for position, hit in enumerate(hits):
        if hit.heading.level == SECTION:
            section = hit.heading.title
        if not hit.heading.keep:
            continue
        end = hits[position + 1].first_line if position + 1 < len(hits) else len(lines)
        block = _build_block(lines, hit, end, section)
        if block is not None:
            blocks.append(block)
    return blocks


def _lines(pages: list[str]) -> list[_Line]:
    lines: list[_Line] = []
    for page_number, page in enumerate(pages, start=1):
        text = strip_lines(normalize_text(page), _NOISE)
        previous_blank = True
        for raw_line in text.split("\n"):
            stripped = raw_line.strip()
            lines.append(_Line(page_number, stripped, previous_blank))
            previous_blank = not stripped
    return lines


def _locate_headings(lines: list[_Line], headings: tuple[Heading, ...]) -> list[_Hit]:
    hits: list[_Hit] = []
    cursor = 0
    previous = "the start of the document"
    for heading in headings:
        hit = _find_heading(lines, heading, cursor)
        if hit is None:
            raise ContractError(
                f"The HIPAA summary has no heading {heading.title!r} after {previous!r}. "
                "Check that docs/ holds the HHS summary PDF, or update HIPAA_HEADINGS."
            )
        hits.append(hit)
        cursor = hit.body_start
        previous = heading.title
    return hits


def _find_heading(lines: list[_Line], heading: Heading, cursor: int) -> _Hit | None:
    for index in range(cursor, len(lines)):
        if not lines[index].starts_paragraph:
            continue
        if heading.level == SECTION:
            hit = _match_section(lines, index, heading)
        else:
            hit = _match_run_in(lines, index, heading)
        if hit is not None:
            return hit
    return None


def _match_section(lines: list[_Line], index: int, heading: Heading) -> _Hit | None:
    """Match a section heading set alone, possibly wrapped over several short lines."""
    parts: list[str] = []
    for offset in range(_MAX_HEADING_LINES):
        position = index + offset
        if position >= len(lines) or not lines[position].text:
            return None
        parts.append(lines[position].text)
        if " ".join(" ".join(parts).split()) == heading.title:
            following = position + 1
            if _ends_heading(lines, following):
                return _Hit(heading, index, following, "")
            return None
    return None


def _ends_heading(lines: list[_Line], following: int) -> bool:
    """True when the line after a candidate heading is blank, starts a page, or does not exist."""
    return following >= len(lines) or not lines[following].text or lines[following].starts_paragraph


def _match_run_in(lines: list[_Line], index: int, heading: Heading) -> _Hit | None:
    """Match a subsection heading that opens a paragraph: `Title.` then the paragraph text."""
    title = r"\s+".join(re.escape(word) for word in heading.title.split())
    pattern = re.compile(rf"^(?:\(\d+\)\s+)?{title}\d*\s*\.(?:\s+(.*))?$")
    match = pattern.match(lines[index].text)
    if match is None:
        return None
    return _Hit(heading, index, index + 1, (match.group(1) or "").strip())


def _build_block(lines: list[_Line], hit: _Hit, end: int, section: str) -> Block | None:
    body = [hit.remainder, *(line.text for line in lines[hit.body_start : end])]
    text = join_wrapped_lines("\n".join(body))
    if not text:
        return None
    page = lines[hit.first_line].page
    title = hit.heading.title
    if hit.heading.level == SECTION:
        breadcrumb = (CITATION_NAME, title)
    else:
        breadcrumb = (CITATION_NAME, section, title)
    return Block(DOC_ID, f"{CITATION_NAME}, {title}, p. {page}", breadcrumb, text, page)
