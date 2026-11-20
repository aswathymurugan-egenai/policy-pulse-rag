"""Split Regulation (EU) 2016/679 into citation blocks.

Blocks are recitals, definitions, article paragraphs, and the lettered points under a paragraph.
Every page ends with an Official Journal footer line, and the page's footnotes follow it, so
everything from the footer on is dropped. That position rule keeps a footnote such as "(4) Directive
95/46/EC ..." from being read as the next recital.
"""

import re
from dataclasses import dataclass, field

from ..blocks import Block
from ..errors import ContractError
from ..extract import join_wrapped_lines, normalize_text

DOC_ID = "gdpr"
CITATION_NAME = "GDPR"
DEFINITIONS_ARTICLE = 4

_FOOTER = re.compile(
    r"^\d{1,2}\.\d{1,2}\.\d{4}\s+L\s+119/\d+\s+Official Journal of the European Union\s+EN$"
)
_RECITALS_START = "Whereas:"
_OPERATIVE_START = "HAVE ADOPTED THIS REGULATION:"
_CLOSING = re.compile(r"^Done at Brussels")
_CHAPTER = re.compile(r"^CHAPTER ([IVXLC]+)$")
_SECTION = re.compile(r"^Section (\d+)$")
_ARTICLE = re.compile(r"^Article (\d+)$")
_RECITAL = re.compile(r"^\((\d{1,3})\)\s+(.*)$")
_PARAGRAPH = re.compile(r"^(\d{1,2})\.\s+(.*)$")
_POINT = re.compile(r"^\(([a-z])\)\s+(.*)$")
_DEFINITION = re.compile(r"^\((\d{1,2})\)\s+(.*)$")


def split_gdpr(pages: list[str]) -> list[Block]:
    """Split the page texts of the GDPR PDF into recital and article blocks."""
    lines = _body_lines(pages)
    operative_start = _index_of(lines, _OPERATIVE_START)
    recitals_start = _index_of(lines, _RECITALS_START)
    closing = next((i for i, line in enumerate(lines) if _CLOSING.match(line)), len(lines))
    recitals = _split_recitals(lines[recitals_start + 1 : operative_start])
    articles = _ArticleSplitter().split(lines[operative_start + 1 : closing])
    return recitals + articles


def _body_lines(pages: list[str]) -> list[str]:
    lines: list[str] = []
    for page in pages:
        for raw_line in normalize_text(page).split("\n"):
            line = raw_line.strip()
            if _FOOTER.match(line):
                break
            if line:
                lines.append(line)
    return lines


def _index_of(lines: list[str], marker: str) -> int:
    for index, line in enumerate(lines):
        if line == marker:
            return index
    raise ContractError(
        f"The GDPR text has no line {marker!r}. Check that docs/ holds the Official Journal PDF."
    )


def _split_recitals(lines: list[str]) -> list[Block]:
    """Split recitals. The first `(n)` line starts the sequence; each later one must be n + 1."""
    blocks: list[Block] = []
    number: int | None = None
    current: list[str] | None = None
    for line in lines:
        match = _RECITAL.match(line)
        if match and (number is None or int(match.group(1)) == number + 1):
            _close_recital(blocks, number, current)
            number = int(match.group(1))
            current = [match.group(2)]
        elif current is not None:
            current.append(line)
    _close_recital(blocks, number, current)
    return blocks


def _close_recital(blocks: list[Block], number: int | None, lines: list[str] | None) -> None:
    if number is None or lines is None:
        return
    label = f"{CITATION_NAME} Recital {number}"
    text = join_wrapped_lines("\n".join(lines))
    blocks.append(Block(DOC_ID, label, (CITATION_NAME, f"Recital {number}"), text))


@dataclass
class _Unit:
    label: str
    breadcrumb: tuple[str, ...]
    lines: list[str] = field(default_factory=list)


@dataclass
class _ArticleSplitter:
    """Walk the operative text line by line and emit one block per citation unit."""

    blocks: list[Block] = field(default_factory=list)
    chapter: str | None = None
    section: str | None = None
    article: int = 0
    article_heading: str = ""
    last_paragraph: int = 0
    last_point: str | None = None
    last_definition: int = 0
    unit: _Unit | None = None

    def split(self, lines: list[str]) -> list[Block]:
        index = 0
        while index < len(lines):
            index = self._consume(lines, index)
        self._close_unit()
        return self.blocks

    def _consume(self, lines: list[str], index: int) -> int:
        line = lines[index]
        if match := _CHAPTER.match(line):
            title, next_index = _read_title(lines, index + 1)
            self._close_unit()
            self.chapter, self.section, self.article = f"Chapter {match.group(1)} {title}", None, 0
            return next_index
        if match := _SECTION.match(line):
            title, next_index = _read_title(lines, index + 1)
            self._close_unit()
            self.section = f"Section {match.group(1)} {title}"
            return next_index
        if match := _ARTICLE.match(line):
            title, next_index = _read_title(lines, index + 1)
            self._close_unit()
            self._start_article(int(match.group(1)), title)
            return next_index
        self._consume_text(line)
        return index + 1

    def _start_article(self, number: int, title: str) -> None:
        self.article = number
        self.article_heading = f"Article {number} {title}"
        self.last_paragraph, self.last_point, self.last_definition = 0, None, 0

    def _consume_text(self, line: str) -> None:
        if self.article == 0:
            return
        if (match := _PARAGRAPH.match(line)) and int(match.group(1)) == self.last_paragraph + 1:
            self._start_paragraph(match.group(2))
        elif self._is_definition(line):
            self._start_definition(_DEFINITION.match(line).group(2))
        elif (match := _POINT.match(line)) and match.group(1) == _next_letter(self.last_point):
            self._start_point(match.group(1), match.group(2))
        elif self.unit is None:
            self._open_unit(f"{CITATION_NAME} Art. {self.article}", (), line)
        else:
            self.unit.lines.append(line)

    def _is_definition(self, line: str) -> bool:
        match = _DEFINITION.match(line)
        return (
            self.article == DEFINITIONS_ARTICLE
            and match is not None
            and int(match.group(1)) == self.last_definition + 1
        )

    def _start_paragraph(self, first_line: str) -> None:
        self._close_unit()
        self.last_paragraph += 1
        self.last_point = None
        number = self.last_paragraph
        self._open_unit(
            f"{CITATION_NAME} Art. {self.article}({number})", (f"Paragraph {number}",), first_line
        )

    def _start_definition(self, first_line: str) -> None:
        self._close_unit()
        self.last_definition += 1
        self.last_point = None
        number = self.last_definition
        self._open_unit(
            f"{CITATION_NAME} Art. {self.article}({number})", (f"Definition {number}",), first_line
        )

    def _start_point(self, letter: str, first_line: str) -> None:
        self._close_unit()
        self.last_point = letter
        label = f"{CITATION_NAME} Art. {self.article}"
        crumbs: tuple[str, ...] = ()
        parent_number, parent_name = self._point_parent()
        if parent_number:
            label += f"({parent_number})"
            crumbs = (f"{parent_name} {parent_number}",)
        self._open_unit(f"{label}({letter})", (*crumbs, f"Point ({letter})"), first_line)

    def _point_parent(self) -> tuple[int, str]:
        """The numbered unit a point belongs to: a definition in Article 4, else a paragraph."""
        if self.article == DEFINITIONS_ARTICLE and self.last_definition:
            return self.last_definition, "Definition"
        return self.last_paragraph, "Paragraph"

    def _open_unit(self, label: str, crumbs: tuple[str, ...], first_line: str) -> None:
        context = tuple(part for part in (self.chapter, self.section) if part)
        breadcrumb = (CITATION_NAME, *context, self.article_heading, *crumbs)
        self.unit = _Unit(label, breadcrumb, [first_line])

    def _close_unit(self) -> None:
        if self.unit is None:
            return
        text = join_wrapped_lines("\n".join(self.unit.lines))
        if text:
            self.blocks.append(Block(DOC_ID, self.unit.label, self.unit.breadcrumb, text))
        self.unit = None


def _read_title(lines: list[str], start: int) -> tuple[str, int]:
    """Read a heading title that may wrap. Continuation lines start in lowercase."""
    if start >= len(lines):
        raise ContractError("The GDPR text ends right after a chapter, section or article heading.")
    parts = [lines[start]]
    index = start + 1
    while index < len(lines) and lines[index][:1].islower():
        parts.append(lines[index])
        index += 1
    return join_wrapped_lines("\n".join(parts)), index


def _next_letter(last: str | None) -> str:
    return "a" if last is None else chr(ord(last) + 1)
