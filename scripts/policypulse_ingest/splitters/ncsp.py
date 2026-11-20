"""Split the National Cyber Security Policy 2013 into citation blocks.

The policy has a numbered Preamble, a Vision, a Mission, numbered Objectives, lettered Strategies A
to N made of numbered items, and a closing Operationalisation section. Each Preamble paragraph,
Objective and Strategy item is a block. A strategy without items is one block.
"""

import re
from dataclasses import dataclass, field

from ..blocks import Block
from ..extract import join_wrapped_lines, normalize_text, strip_lines

DOC_ID = "ncsp"
CITATION_NAME = "NCSP 2013"

_NOISE = [
    re.compile(r"^\s*Page \d+ of \d+\s*$"),
    re.compile(r"^\s*\d+ISO / IEC \d+-\d+\s*$"),
]
_PREAMBLE = re.compile(r"^Preamble$")
_VISION = re.compile(r"^I\.\s+Vision$")
_MISSION = re.compile(r"^II\.\s+Mission$")
_OBJECTIVES = re.compile(r"^III\.\s+Objectives$")
_STRATEGIES = re.compile(r"^IV\.\s+Strategies$")
_OPERATIONALISATION = re.compile(r"^V\.\s+Operationalisation of the Policy$")
_PARAGRAPH = re.compile(r"^(\d{1,2})\.\s+(.*)$")
_ITEM = re.compile(r"^(\d{1,2})\)\s+(.*)$")
_STRATEGY = re.compile(r"^([A-N])\.\s+(.*)$")


def split_ncsp(pages: list[str]) -> list[Block]:
    """Split the page texts of the NCSP PDF into Preamble, Objective and Strategy blocks."""
    lines = _clean_lines(pages)
    return _PolicySplitter().split(lines)


def _clean_lines(pages: list[str]) -> list[str]:
    text = strip_lines(normalize_text("\n".join(pages)), _NOISE)
    return [line.strip() for line in text.split("\n") if line.strip()]


@dataclass
class _PolicySplitter:
    """Walk the policy text line by line, tracking the section and the numbered item."""

    blocks: list[Block] = field(default_factory=list)
    section: str = ""
    strategy_letter: str | None = None
    strategy_title: str = ""
    last_number: int = 0
    label: str = ""
    breadcrumb: tuple[str, ...] = ()
    unit_lines: list[str] = field(default_factory=list)

    def split(self, lines: list[str]) -> list[Block]:
        index = 0
        while index < len(lines):
            index = self._consume(lines, index)
        self._close_unit()
        return self.blocks

    def _consume(self, lines: list[str], index: int) -> int:
        line = lines[index]
        if _PREAMBLE.match(line):
            self._enter("preamble", "")
        elif _VISION.match(line):
            self._enter("vision", f"{CITATION_NAME}, Vision", (CITATION_NAME, "Vision"))
        elif _MISSION.match(line):
            self._enter("mission", f"{CITATION_NAME}, Mission", (CITATION_NAME, "Mission"))
        elif _OBJECTIVES.match(line):
            self._enter("objectives", "")
        elif _STRATEGIES.match(line):
            self._enter("strategies", "")
        elif _OPERATIONALISATION.match(line):
            self._enter(
                "operationalisation",
                f"{CITATION_NAME}, Operationalisation",
                (CITATION_NAME, "Operationalisation"),
            )
        elif self.section == "strategies" and self._is_strategy_heading(line):
            return self._start_strategy(lines, index)
        elif self._is_numbered_unit(line):
            self._start_numbered_unit(line)
        else:
            self.unit_lines.append(line)
        return index + 1

    def _enter(self, section: str, label: str, breadcrumb: tuple[str, ...] = ()) -> None:
        self._close_unit()
        self.section = section
        self.last_number = 0
        self.strategy_letter = None
        self.label, self.breadcrumb = label, breadcrumb

    def _is_strategy_heading(self, line: str) -> bool:
        match = _STRATEGY.match(line)
        if match is None:
            return False
        # Strategy letters only ever advance, which keeps a wrapped "I. " or "V. " line out.
        return self.strategy_letter is None or match.group(1) > self.strategy_letter

    def _start_strategy(self, lines: list[str], index: int) -> int:
        match = _STRATEGY.match(lines[index])
        title_parts = [match.group(2)]
        next_index = index + 1
        while next_index < len(lines) and lines[next_index][:1].islower():
            title_parts.append(lines[next_index])
            next_index += 1
        self._close_unit()
        self.strategy_letter = match.group(1)
        self.strategy_title = join_wrapped_lines("\n".join(title_parts))
        self.last_number = 0
        self.label = f"{CITATION_NAME}, Strategy {self.strategy_letter}"
        self.breadcrumb = (
            CITATION_NAME,
            "Strategies",
            f"Strategy {self.strategy_letter} {self.strategy_title}",
        )
        return next_index

    def _is_numbered_unit(self, line: str) -> bool:
        pattern = _PARAGRAPH if self.section == "preamble" else _ITEM
        match = pattern.match(line)
        if self.section not in ("preamble", "objectives", "strategies") or match is None:
            return False
        # The first numbered line starts the sequence; each later one must be the previous plus one.
        return self.last_number == 0 or int(match.group(1)) == self.last_number + 1

    def _start_numbered_unit(self, line: str) -> None:
        if self.section == "strategies":
            parent_label, parent_breadcrumb = self._strategy_parent()
        else:
            parent_label, parent_breadcrumb = "", ()
        self._close_unit()
        pattern = _PARAGRAPH if self.section == "preamble" else _ITEM
        match = pattern.match(line)
        self.last_number = int(match.group(1))
        number = self.last_number
        if self.section == "preamble":
            self.label = f"{CITATION_NAME}, Preamble, para {number}"
            self.breadcrumb = (CITATION_NAME, "Preamble", f"Paragraph {number}")
        elif self.section == "objectives":
            self.label = f"{CITATION_NAME}, Objective {number}"
            self.breadcrumb = (CITATION_NAME, "Objectives", f"Objective {number}")
        else:
            self.label = f"{parent_label}, item {number}"
            self.breadcrumb = (*parent_breadcrumb, f"Item {number}")
        self.unit_lines = [match.group(2)]

    def _strategy_parent(self) -> tuple[str, tuple[str, ...]]:
        return f"{CITATION_NAME}, Strategy {self.strategy_letter}", (
            CITATION_NAME,
            "Strategies",
            f"Strategy {self.strategy_letter} {self.strategy_title}",
        )

    def _close_unit(self) -> None:
        if self.label and self.unit_lines:
            text = join_wrapped_lines("\n".join(self.unit_lines))
            self.blocks.append(Block(DOC_ID, self.label, self.breadcrumb, text))
        self.unit_lines = []
        self.label = ""

