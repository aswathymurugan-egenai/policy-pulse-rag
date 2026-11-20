"""The registry of source documents, source file resolution, and the contract gate.

Each entry says which file holds the document, how its citation labels look, how to split it, and
what the split must contain. The contract gate runs on the split before anything is rendered or
uploaded, so a splitter that misreads a PDF fails here and never reaches the corpus.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .blocks import Block
from .errors import ContractError, UsageError
from .extract import read_pdf_pages
from .splitters.gdpr import split_gdpr
from .splitters.headings import SUBSECTION
from .splitters.hipaa import CITATION_NAME as HIPAA_CITATION
from .splitters.hipaa import HIPAA_HEADINGS, split_hipaa
from .splitters.ncsp import split_ncsp
from .splitters.registration_api import split_registration_api
from .splitters.road_safety import CITATION_NAME as ROAD_SAFETY_CITATION
from .splitters.road_safety import INTRODUCTION_LABEL, ROAD_SAFETY_HEADINGS, split_road_safety

Splitter = Callable[[list[str]], list[Block]]

_MAX_PROBLEM_EXAMPLES = 10


@dataclass(frozen=True)
class SourceDocument:
    """One source document and what a correct split of it must contain.

    A required label is met by a block label equal to it, or one that extends it at a `(` or `,`
    boundary: `GDPR Art. 5` is met by `GDPR Art. 5(1)(c)`.
    """

    doc_id: str
    citation_name: str
    file_names: tuple[str, ...]
    label_pattern: re.Pattern[str]
    split: Splitter
    required_labels: tuple[str, ...]
    block_count_range: tuple[int, int]


def _gdpr_required_labels() -> tuple[str, ...]:
    articles = tuple(f"GDPR Art. {number}" for number in range(1, 100))
    recitals = tuple(f"GDPR Recital {number}" for number in range(1, 174))
    named = (
        "GDPR Art. 4(7)",
        "GDPR Art. 5(1)(c)",
        "GDPR Art. 33(1)",
        "GDPR Art. 83(5)",
        "GDPR Art. 83(6)",
    )
    return (*articles, *recitals, *named)


def _ncsp_required_labels() -> tuple[str, ...]:
    preamble = tuple(f"NCSP 2013, Preamble, para {number}" for number in range(1, 8))
    objectives = tuple(f"NCSP 2013, Objective {number}" for number in range(1, 15))
    strategies = tuple(f"NCSP 2013, Strategy {letter}" for letter in "ABCDEFGHIJKLMN")
    fixed = ("NCSP 2013, Vision", "NCSP 2013, Mission", "NCSP 2013, Operationalisation")
    return (*preamble, *objectives, *strategies, *fixed)


def _hipaa_required_labels() -> tuple[str, ...]:
    subsections = tuple(
        f"{HIPAA_CITATION}, {heading.title}"
        for heading in HIPAA_HEADINGS
        if heading.level == SUBSECTION
    )
    return (f"{HIPAA_CITATION}, Introduction", *subsections)


def _road_safety_required_labels() -> tuple[str, ...]:
    headings = tuple(f"{ROAD_SAFETY_CITATION}, {heading.title}" for heading in ROAD_SAFETY_HEADINGS)
    return (INTRODUCTION_LABEL, *headings)


def _road_safety_split(pages: list[str]) -> list[Block]:
    return split_road_safety(pages, ROAD_SAFETY_HEADINGS)


def _hipaa_split(pages: list[str]) -> list[Block]:
    return split_hipaa(pages, HIPAA_HEADINGS)


GDPR = SourceDocument(
    doc_id="gdpr",
    citation_name="GDPR",
    file_names=("gdpr_regulation_2016_679.pdf",),
    label_pattern=re.compile(r"^GDPR (Recital \d+|Art\. \d+(\(\d+\))?(\([a-z]\))?)$"),
    split=split_gdpr,
    required_labels=_gdpr_required_labels(),
    block_count_range=(850, 1040),
)
HIPAA = SourceDocument(
    doc_id="hipaa",
    citation_name=HIPAA_CITATION,
    file_names=("privacysummary.pdf",),
    label_pattern=re.compile(r"^HIPAA Privacy Rule Summary, .+, p\. \d+$"),
    split=_hipaa_split,
    required_labels=_hipaa_required_labels(),
    block_count_range=(60, 85),
)
NCSP = SourceDocument(
    doc_id="ncsp",
    citation_name="NCSP 2013",
    file_names=("national_cyber_security_policy_2013.pdf",),
    label_pattern=re.compile(
        r"^NCSP 2013, (Preamble, para \d+|Vision|Mission|Objective \d+"
        r"|Strategy [A-N](, item \d+)?|Operationalisation)$"
    ),
    split=split_ncsp,
    required_labels=_ncsp_required_labels(),
    block_count_range=(75, 90),
)
ROAD_SAFETY = SourceDocument(
    doc_id="road_safety",
    citation_name=ROAD_SAFETY_CITATION,
    file_names=("national_road_safety_policy_2010.pdf",),
    label_pattern=re.compile(r"^Road Safety Policy, .+$"),
    split=_road_safety_split,
    required_labels=_road_safety_required_labels(),
    block_count_range=(14, 16),
)
REGISTRATION_API = SourceDocument(
    doc_id="registration_api",
    citation_name="Registration API",
    file_names=("customer_registration_api_spec.md", "customer_registration_api_spec.pdf"),
    label_pattern=re.compile(r"^Registration API, .+$"),
    split=split_registration_api,
    required_labels=(),
    block_count_range=(1, 2000),
)

DOCUMENTS: tuple[SourceDocument, ...] = (GDPR, HIPAA, NCSP, ROAD_SAFETY, REGISTRATION_API)


def document_by_id(doc_id: str) -> SourceDocument:
    """Return the registry entry for a doc id."""
    for document in DOCUMENTS:
        if document.doc_id == doc_id:
            return document
    raise KeyError(f"No source document has the id {doc_id!r}.")


def resolve_sources(
    docs_dir: Path, documents: tuple[SourceDocument, ...] = DOCUMENTS
) -> dict[str, Path]:
    """Map each doc id to its file in docs_dir, or raise a UsageError naming every problem."""
    sources: dict[str, Path] = {}
    problems: list[str] = []
    for document in documents:
        present = [docs_dir / name for name in document.file_names if (docs_dir / name).is_file()]
        accepted = " or ".join(document.file_names)
        if not present:
            problems.append(f"missing {accepted}")
        elif len(present) > 1:
            names = " and ".join(path.name for path in present)
            problems.append(f"ambiguous: {names} are both present; keep one of {accepted}")
        else:
            sources[document.doc_id] = present[0]
    if problems:
        raise UsageError(f"Source files in {docs_dir} are not usable: " + "; ".join(problems) + ".")
    return sources


def load_pages(path: Path) -> list[str]:
    """Read a source file as page texts. A PDF gives one text per page; markdown gives one page."""
    if path.suffix.lower() == ".pdf":
        return read_pdf_pages(path)
    return [path.read_text(encoding="utf-8")]


def check_contract(document: SourceDocument, blocks: list[Block]) -> None:
    """Raise a ContractError naming everything that is wrong with the split of a document."""
    problems: list[str] = []
    problems += _label_pattern_problems(document, blocks)
    problems += _missing_label_problems(document, blocks)
    low, high = document.block_count_range
    if not low <= len(blocks) <= high:
        problems.append(f"{len(blocks)} blocks, expected {low} to {high}")
    if problems:
        raise ContractError(f"{document.citation_name} breaks its contract: " + "; ".join(problems))


def _label_pattern_problems(document: SourceDocument, blocks: list[Block]) -> list[str]:
    odd = [block.label for block in blocks if not document.label_pattern.match(block.label)]
    if not odd:
        return []
    pattern = document.label_pattern.pattern
    return [f"{len(odd)} labels do not match {pattern!r}, for example {odd[:3]}"]


def _missing_label_problems(document: SourceDocument, blocks: list[Block]) -> list[str]:
    labels = [block.label for block in blocks]
    missing = [
        required
        for required in document.required_labels
        if not any(_covers(label, required) for label in labels)
    ]
    if not missing:
        return []
    shown = ", ".join(missing[:_MAX_PROBLEM_EXAMPLES])
    hidden = len(missing) - _MAX_PROBLEM_EXAMPLES
    more = f" and {hidden} more" if hidden > 0 else ""
    return [f"missing labels {shown}{more}"]


def _covers(label: str, required: str) -> bool:
    return label == required or label.startswith((required + "(", required + ","))
