"""Bring the Vertex AI RAG corpus to the state the rendered documents describe.

The sync is safe to run twice. A file is named `<doc_id>__<sha12>.md`, where the hash covers the
rendered markdown and the chunking settings, so a file with the current name is the current
content and is skipped. A changed document uploads the new file, waits for it to become ACTIVE, and
only then deletes the old one.

`RagClient` is the network boundary. `AgentPlatformRagClient` implements it over the
`agentplatform` SDK, and tests use an in-memory fake.
"""

import hashlib
import mimetypes
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .errors import SyncError

if TYPE_CHECKING:
    from agentplatform import types as sdk_types

CORPUS_DISPLAY_NAME = "policypulse-5docs-corpus"
CORPUS_DESCRIPTION = (
    "PolicyPulse: GDPR, HIPAA Privacy Rule Summary, NCSP 2013, "
    "National Road Safety Policy 2010, Customer Registration API spec"
)
EMBEDDING_MODEL_PATH = "publishers/google/models/text-embedding-005"
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 200
SPLITTER_VERSION = 1

FILE_ACTIVE = "ACTIVE"
FILE_ERROR = "ERROR"
POLL_INTERVAL_SECONDS = 5
WAIT_TIMEOUT_SECONDS = 600

_HASH_LENGTH = 12
_FILE_NAME = re.compile(r"^(?P<doc_id>[a-z_]+)__(?P<hash>[0-9a-f]{12})\.md$")


@dataclass(frozen=True)
class RemoteCorpus:
    """A corpus as the service reports it."""

    name: str
    display_name: str
    embedding_endpoint: str | None


@dataclass(frozen=True)
class RemoteFile:
    """A file in a corpus. `state` is ACTIVE, ERROR, or anything else while it is processing."""

    name: str
    display_name: str
    state: str


@dataclass(frozen=True)
class LocalDocument:
    """A rendered document ready to upload, with the hash of its content and chunk settings."""

    doc_id: str
    path: Path
    content_hash: str

    @property
    def display_name(self) -> str:
        return f"{self.doc_id}__{self.content_hash}.md"


class RagClient(Protocol):
    """The calls the sync makes against Vertex AI RAG Engine."""

    def list_corpora(self) -> list[RemoteCorpus]: ...

    def create_corpus(
        self, display_name: str, description: str, embedding_endpoint: str
    ) -> RemoteCorpus: ...

    def get_corpus(self, name: str) -> RemoteCorpus: ...

    def delete_corpus(self, name: str) -> None: ...

    def list_files(self, corpus_name: str) -> list[RemoteFile]: ...

    def upload_file(self, corpus_name: str, path: Path, display_name: str) -> RemoteFile: ...

    def get_file(self, name: str) -> RemoteFile: ...

    def delete_file(self, name: str) -> None: ...


class ActionKind(Enum):
    """What the sync does about one file."""

    SKIP = "skip"
    UPLOAD = "upload"
    WAIT = "wait"
    DELETE_BEFORE = "delete_before"
    DELETE_AFTER = "delete_after"


@dataclass(frozen=True)
class FileAction:
    doc_id: str
    kind: ActionKind
    remote: RemoteFile | None = None


@dataclass(frozen=True)
class SyncPlan:
    actions: list[FileAction]
    strays: list[RemoteFile]


@dataclass(frozen=True)
class DocOutcome:
    """What happened to one document: skip, upload, replace (upload plus delete), or repair."""

    doc_id: str
    action: str
    display_name: str


@dataclass(frozen=True)
class SyncResult:
    corpus: RemoteCorpus
    outcomes: list[DocOutcome]
    strays: list[RemoteFile]
    stored_embedding_endpoint: str | None = None
    corpus_created: bool = False


def expected_embedding_endpoint(project: str, location: str) -> str:
    """The text-embedding-005 endpoint in the corpus region."""
    return f"projects/{project}/locations/{location}/{EMBEDDING_MODEL_PATH}"


def content_hash(
    markdown: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    splitter_version: int = SPLITTER_VERSION,
) -> str:
    """Hash of the rendered markdown and the settings that shape its chunks, 12 hex characters."""
    settings = f"\nchunk_size={chunk_size} chunk_overlap={chunk_overlap} "
    settings += f"splitter_version={splitter_version}"
    digest = hashlib.sha256(markdown.encode("utf-8") + settings.encode("utf-8"))
    return digest.hexdigest()[:_HASH_LENGTH]


def plan_file_actions(remote_files: list[RemoteFile], local_docs: list[LocalDocument]) -> SyncPlan:
    """Decide, per document, what to do about the files the corpus already holds.

    A file named for a document id that is not in local_docs is a stray and is left alone.
    """
    known_ids = {doc.doc_id for doc in local_docs}
    by_doc: dict[str, list[RemoteFile]] = {doc_id: [] for doc_id in known_ids}
    strays: list[RemoteFile] = []
    for remote in remote_files:
        match = _FILE_NAME.match(remote.display_name)
        if match and match.group("doc_id") in known_ids:
            by_doc[match.group("doc_id")].append(remote)
        else:
            strays.append(remote)
    actions: list[FileAction] = []
    for doc in local_docs:
        actions += _plan_document(doc, by_doc[doc.doc_id])
    return SyncPlan(actions, strays)


def _plan_document(doc: LocalDocument, files: list[RemoteFile]) -> list[FileAction]:
    current = [f for f in files if f.display_name == doc.display_name]
    active_current = next((f for f in current if f.state == FILE_ACTIVE), None)
    if active_current is not None:
        extras = [f for f in files if f is not active_current]
        return [FileAction(doc.doc_id, ActionKind.SKIP, active_current)] + [
            FileAction(doc.doc_id, ActionKind.DELETE_AFTER, extra) for extra in extras
        ]
    errored = [f for f in files if f.state == FILE_ERROR]
    processing = next((f for f in current if f.state != FILE_ERROR), None)
    superseded = [f for f in files if f not in errored and f is not processing]
    actions = [FileAction(doc.doc_id, ActionKind.DELETE_BEFORE, f) for f in errored]
    if processing is not None:
        actions.append(FileAction(doc.doc_id, ActionKind.WAIT, processing))
    else:
        actions.append(FileAction(doc.doc_id, ActionKind.UPLOAD))
    return actions + [FileAction(doc.doc_id, ActionKind.DELETE_AFTER, f) for f in superseded]


def sync_corpus(
    client: RagClient,
    docs: list[LocalDocument],
    *,
    project: str,
    location: str,
    recreate: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> SyncResult:
    """Make the corpus hold exactly the current files for docs. Running it again changes nothing."""
    endpoint = expected_embedding_endpoint(project, location)
    corpus, created = _find_or_create_corpus(client, endpoint, recreate)
    plan = plan_file_actions(client.list_files(corpus.name), docs)
    outcomes = _execute_plan(client, corpus, docs, plan, sleep, clock)
    stored = client.get_corpus(corpus.name).embedding_endpoint
    return SyncResult(corpus, outcomes, plan.strays, stored, created)


def _find_or_create_corpus(
    client: RagClient, endpoint: str, recreate: bool
) -> tuple[RemoteCorpus, bool]:
    matching = [c for c in client.list_corpora() if c.display_name == CORPUS_DISPLAY_NAME]
    if recreate:
        for corpus in matching:
            _delete_corpus_with_files(client, corpus)
        matching = []
    if len(matching) > 1:
        names = ", ".join(corpus.name for corpus in matching)
        raise SyncError(
            f"{len(matching)} corpora are named {CORPUS_DISPLAY_NAME!r}: {names}. "
            "Delete the extras in the Google Cloud console, then run again."
        )
    if matching:
        _check_embedding_model(matching[0])
        return matching[0], False
    created = client.create_corpus(CORPUS_DISPLAY_NAME, CORPUS_DESCRIPTION, endpoint)
    return created, True


def _delete_corpus_with_files(client: RagClient, corpus: RemoteCorpus) -> None:
    # The service has no force option on corpus deletion, so the files go first.
    for remote in client.list_files(corpus.name):
        client.delete_file(remote.name)
    client.delete_corpus(corpus.name)


def _check_embedding_model(corpus: RemoteCorpus) -> None:
    endpoint = corpus.embedding_endpoint or ""
    if not endpoint.endswith(EMBEDDING_MODEL_PATH):
        raise SyncError(
            f"Corpus {corpus.name} embeds with {endpoint or 'an unknown model'}, not "
            f"{EMBEDDING_MODEL_PATH}. Run with --recreate to rebuild it."
        )


def _execute_plan(
    client: RagClient,
    corpus: RemoteCorpus,
    docs: list[LocalDocument],
    plan: SyncPlan,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> list[DocOutcome]:
    outcomes: list[DocOutcome] = []
    for doc in docs:
        actions = [action for action in plan.actions if action.doc_id == doc.doc_id]
        outcomes.append(_execute_document(client, corpus, doc, actions, sleep, clock))
    return outcomes


def _execute_document(
    client: RagClient,
    corpus: RemoteCorpus,
    doc: LocalDocument,
    actions: list[FileAction],
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> DocOutcome:
    uploaded = False
    deleted_old = False
    for action in actions:
        if action.kind in (ActionKind.DELETE_BEFORE, ActionKind.DELETE_AFTER):
            client.delete_file(action.remote.name)
            deleted_old = True
        elif action.kind is ActionKind.UPLOAD:
            _upload_and_activate(client, corpus, doc, sleep, clock)
            uploaded = True
        elif action.kind is ActionKind.WAIT:
            settled = _wait_until_active(client, action.remote, sleep, clock)
            if settled.state != FILE_ACTIVE:
                client.delete_file(settled.name)
                _upload_and_activate(client, corpus, doc, sleep, clock)
            uploaded = True
    return DocOutcome(doc.doc_id, _outcome_name(uploaded, deleted_old), doc.display_name)


def _outcome_name(uploaded: bool, deleted_old: bool) -> str:
    if uploaded:
        return "replace" if deleted_old else "upload"
    return "repair" if deleted_old else "skip"


def _upload_and_activate(
    client: RagClient,
    corpus: RemoteCorpus,
    doc: LocalDocument,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> RemoteFile:
    """Upload a document and wait for it. One ERROR is retried once; a second stops the run."""
    for attempt in (1, 2):
        uploaded = client.upload_file(corpus.name, doc.path, doc.display_name)
        settled = _wait_until_active(client, uploaded, sleep, clock)
        if settled.state == FILE_ACTIVE:
            return settled
        if attempt == 2:
            raise SyncError(
                f"{doc.display_name} ended in state {settled.state} after a second upload. "
                f"Check the file in the Google Cloud console: {settled.name}."
            )
        client.delete_file(settled.name)
    raise AssertionError("unreachable")


def _wait_until_active(
    client: RagClient,
    remote: RemoteFile,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> RemoteFile:
    """Poll until the file is ACTIVE or ERROR. Raise if it is neither within ten minutes."""
    deadline = clock() + WAIT_TIMEOUT_SECONDS
    current = remote
    while current.state not in (FILE_ACTIVE, FILE_ERROR):
        if clock() >= deadline:
            raise SyncError(
                f"{remote.display_name} was still in state {current.state} after "
                f"{WAIT_TIMEOUT_SECONDS // 60} minutes. Wait and run again, or check {remote.name}."
            )
        sleep(POLL_INTERVAL_SECONDS)
        current = client.get_file(remote.name)
    return current


def build_upload_config() -> "sdk_types.UploadRagFileConfig":
    """Chunking settings for an upload: fixed-length chunks of CHUNK_SIZE tokens with overlap."""
    from agentplatform import types

    return types.UploadRagFileConfig(
        rag_file_transformation_config=types.RagFileTransformationConfig(
            rag_file_chunking_config=types.RagFileChunkingConfig(
                fixed_length_chunking=types.RagFileChunkingConfigFixedLengthChunking(
                    chunk_size=CHUNK_SIZE,
                    chunk_overlap=CHUNK_OVERLAP,
                ),
            ),
        ),
    )


def build_corpus_spec(
    display_name: str, description: str, embedding_endpoint: str
) -> "sdk_types.RagCorpus":
    """The corpus to create: RAG-managed vector database with the given embedding endpoint."""
    from agentplatform import types

    return types.RagCorpus(
        display_name=display_name,
        description=description,
        vector_db_config=types.RagVectorDbConfig(
            rag_embedding_model_config=types.RagEmbeddingModelConfig(
                vertex_prediction_endpoint=types.RagEmbeddingModelConfigVertexPredictionEndpoint(
                    endpoint=embedding_endpoint,
                ),
            ),
        ),
    )


class AgentPlatformRagClient:
    """RagClient over `agentplatform.Client(...).rag`, handling pagination and result mapping."""

    def __init__(self, project: str, location: str) -> None:
        import agentplatform

        # upload_file guesses the MIME type from the path, and older Pythons do not map .md.
        mimetypes.add_type("text/markdown", ".md")
        self._rag = agentplatform.Client(project=project, location=location).rag

    def list_corpora(self) -> list[RemoteCorpus]:
        from agentplatform import types

        corpora: list[RemoteCorpus] = []
        token: str | None = None
        while True:
            config = types.ListRagCorporaConfig(page_token=token)
            page = self._rag.list_corpora(config=config)
            corpora += [_to_remote_corpus(c) for c in page.rag_corpora or []]
            token = page.next_page_token
            if not token:
                return corpora

    def create_corpus(
        self, display_name: str, description: str, embedding_endpoint: str
    ) -> RemoteCorpus:
        spec = build_corpus_spec(display_name, description, embedding_endpoint)
        return _to_remote_corpus(self._rag.create_corpus(rag_corpus=spec))

    def get_corpus(self, name: str) -> RemoteCorpus:
        return _to_remote_corpus(self._rag.get_corpus(name=name))

    def delete_corpus(self, name: str) -> None:
        self._rag.delete_corpus(name=name)

    def list_files(self, corpus_name: str) -> list[RemoteFile]:
        from agentplatform import types

        files: list[RemoteFile] = []
        token: str | None = None
        while True:
            config = types.ListRagFilesConfig(page_token=token)
            page = self._rag.list_files(name=corpus_name, config=config)
            files += [_to_remote_file(f) for f in page.rag_files or []]
            token = page.next_page_token
            if not token:
                return files

    def upload_file(self, corpus_name: str, path: Path, display_name: str) -> RemoteFile:
        uploaded = self._rag.upload_file(
            corpus_name=corpus_name,
            path=str(path),
            display_name=display_name,
            upload_rag_file_config=build_upload_config(),
        )
        return _to_remote_file(uploaded)

    def get_file(self, name: str) -> RemoteFile:
        return _to_remote_file(self._rag.get_file(name=name))

    def delete_file(self, name: str) -> None:
        self._rag.delete_file(name=name)


def _to_remote_corpus(corpus) -> RemoteCorpus:
    return RemoteCorpus(corpus.name, corpus.display_name or "", _stored_endpoint(corpus))


def _stored_endpoint(corpus) -> str | None:
    """The embedding endpoint the service stored. It may sit under any of three corpus fields."""
    candidates = (
        getattr(getattr(corpus, "vector_db_config", None), "rag_embedding_model_config", None),
        getattr(getattr(corpus, "rag_vector_db_config", None), "rag_embedding_model_config", None),
        getattr(corpus, "rag_embedding_model_config", None),
    )
    for config in candidates:
        endpoint = getattr(getattr(config, "vertex_prediction_endpoint", None), "endpoint", None)
        if endpoint:
            return endpoint
    return None


def _to_remote_file(rag_file) -> RemoteFile:
    state = getattr(getattr(rag_file, "file_status", None), "state", None)
    state_name = getattr(state, "name", None) or "STATE_UNSPECIFIED"
    return RemoteFile(rag_file.name, rag_file.display_name or "", state_name)
