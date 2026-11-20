"""Heading registry entries shared by the splitters that cut a document at known headings."""

from dataclasses import dataclass

SECTION = 1
SUBSECTION = 2


@dataclass(frozen=True)
class Heading:
    """A heading the document is known to contain, in reading order.

    `keep=False` marks a heading that ends the text worth citing, such as a list of endnotes. Its
    text is dropped.
    """

    title: str
    level: int = SECTION
    keep: bool = True
