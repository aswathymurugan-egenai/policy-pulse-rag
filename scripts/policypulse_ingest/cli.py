"""Command line for the ingest: render the source documents, then sync them to the RAG corpus.

Exit codes: 0 on success, 1 on a runtime failure (contract gate, sync), 2 on a usage error (missing
environment value, or a missing or ambiguous source file).
"""

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from .blocks import Block, render_blocks
from .corpus_sync import (
    AgentPlatformRagClient,
    LocalDocument,
    RagClient,
    SyncResult,
    content_hash,
    sync_corpus,
)
from .documents import DOCUMENTS, SourceDocument, check_contract, load_pages, resolve_sources
from .dotenv_file import upsert_env_value
from .errors import ContractError, SyncError, UsageError

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ENV_KEY = "RAG_CORPUS_RESOURCE_NAME"

ClientFactory = Callable[[str, str], RagClient]


@dataclass(frozen=True)
class Settings:
    """Cloud settings the sync needs."""

    project: str
    location: str


def main(
    argv: Sequence[str] | None = None,
    *,
    documents: tuple[SourceDocument, ...] = DOCUMENTS,
    client_factory: ClientFactory = AgentPlatformRagClient,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run the ingest and return the process exit code."""
    args = _parse_args(argv)
    environment = environ if environ is not None else _process_environment()
    try:
        sources = resolve_sources(args.docs_dir, documents)
        local_docs = _render_documents(documents, sources, args.build_dir)
        if args.render_only:
            return 0
        settings = _read_settings(args.env_file, environment)
        client = client_factory(settings.project, settings.location)
        result = sync_corpus(
            client,
            local_docs,
            project=settings.project,
            location=settings.location,
            recreate=args.recreate,
        )
        upsert_env_value(args.env_file, CORPUS_ENV_KEY, result.corpus.name)
        _print_result(result, args.env_file)
        return 0
    except UsageError as error:
        print(f"usage error: {error}", file=sys.stderr)
        return 2
    except (ContractError, SyncError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ingest_corpus.py",
        description="Render the five source documents and sync them to the Vertex AI RAG corpus.",
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="write build/corpus/*.md and stop; no Google Cloud call is made",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="delete the corpus and its files, then build a new corpus from scratch",
    )
    parser.add_argument("--docs-dir", type=Path, default=REPO_ROOT / "docs")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--build-dir", type=Path, default=REPO_ROOT / "build")
    return parser.parse_args(argv)


def _process_environment() -> Mapping[str, str]:
    return os.environ


def _render_documents(
    documents: tuple[SourceDocument, ...], sources: dict[str, Path], build_dir: Path
) -> list[LocalDocument]:
    corpus_dir = build_dir / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    local_docs: list[LocalDocument] = []
    for document in documents:
        blocks = document.split(load_pages(sources[document.doc_id]))
        check_contract(document, blocks)
        markdown = render_blocks(blocks)
        path = corpus_dir / f"{document.doc_id}.md"
        path.write_text(markdown, encoding="utf-8")
        local_docs.append(LocalDocument(document.doc_id, path, content_hash(markdown)))
        print(_render_line(document, blocks, path))
    return local_docs


def _render_line(document: SourceDocument, blocks: list[Block], path: Path) -> str:
    return f"rendered {document.doc_id:<18} {len(blocks):>5} blocks  {path}"


def _read_settings(env_file: Path, environ: Mapping[str, str]) -> Settings:
    file_values = dotenv_values(env_file) if env_file.exists() else {}
    values = {**file_values, **environ}
    project = values.get("GOOGLE_CLOUD_PROJECT")
    location = values.get("RAG_LOCATION") or values.get("GOOGLE_CLOUD_LOCATION")
    if not project:
        raise UsageError(
            f"GOOGLE_CLOUD_PROJECT is not set. Add it to {env_file} or the environment."
        )
    if not location:
        raise UsageError(
            f"RAG_LOCATION is not set, and GOOGLE_CLOUD_LOCATION is not set to fall back on. "
            f"Add RAG_LOCATION to {env_file} or the environment."
        )
    return Settings(project, location)


def _print_result(result: SyncResult, env_file: Path) -> None:
    verb = "created" if result.corpus_created else "reused"
    print(f"corpus {verb}: {result.corpus.name}")
    for outcome in result.outcomes:
        print(f"  {outcome.doc_id:<18} {outcome.action:<8} {outcome.display_name}")
    for stray in result.strays:
        print(f"  stray file left in place: {stray.display_name} ({stray.name})")
    print(f"embedding endpoint stored by the service: {result.stored_embedding_endpoint}")
    print(f"{CORPUS_ENV_KEY} written to {env_file}")
