from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

import agentplatform
import pytest
from agentplatform import types as sdk

from policypulse_ingest.corpus_sync import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CORPUS_DISPLAY_NAME,
    ActionKind,
    AgentPlatformRagClient,
    LocalDocument,
    RemoteCorpus,
    RemoteFile,
    build_corpus_spec,
    build_upload_config,
    content_hash,
    expected_embedding_endpoint,
    plan_file_actions,
    sync_corpus,
)
from policypulse_ingest.errors import SyncError

if TYPE_CHECKING:
    from conftest import FakeClock, FakeRagClient

PROJECT = "demo-project"
LOCATION = "us-east4"
ENDPOINT = expected_embedding_endpoint(PROJECT, LOCATION)
DOC_IDS = ("gdpr", "hipaa", "ncsp", "road_safety", "registration_api")


def local_docs(hash_char: str = "a") -> list[LocalDocument]:
    return [
        LocalDocument(doc_id, Path(f"build/corpus/{doc_id}.md"), hash_char * 12)
        for doc_id in DOC_IDS
    ]


def name_of(doc_id: str, hash_char: str = "a") -> str:
    return f"{doc_id}__{hash_char * 12}.md"


def run_sync(
    client: FakeRagClient,
    clock: FakeClock,
    docs: list[LocalDocument] | None = None,
    recreate: bool = False,
):
    return sync_corpus(
        client,
        docs if docs is not None else local_docs(),
        project=PROJECT,
        location=LOCATION,
        recreate=recreate,
        sleep=clock.sleep,
        clock=clock.clock,
    )


def test_creates_the_corpus_when_none_exists(fake_rag_client: FakeRagClient, fake_clock: FakeClock):
    # Arrange / Act
    result = run_sync(fake_rag_client, fake_clock)

    # Assert
    created = fake_rag_client.calls_named("create_corpus")
    assert created == [("create_corpus", CORPUS_DISPLAY_NAME, ENDPOINT)]
    assert result.corpus.display_name == CORPUS_DISPLAY_NAME
    assert ENDPOINT.endswith("publishers/google/models/text-embedding-005")


def test_reuses_the_single_matching_corpus(fake_rag_client: FakeRagClient, fake_clock: FakeClock):
    # Arrange
    existing = fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, ENDPOINT)

    # Act
    result = run_sync(fake_rag_client, fake_clock)

    # Assert
    assert result.corpus.name == existing.name
    assert not fake_rag_client.calls_named("create_corpus")


def test_fails_when_two_corpora_share_the_display_name(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    first = fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, ENDPOINT)
    second = fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, ENDPOINT)

    # Act / Assert
    with pytest.raises(SyncError) as error:
        run_sync(fake_rag_client, fake_clock)
    assert first.name in str(error.value)
    assert second.name in str(error.value)
    assert not fake_rag_client.calls_named("upload_file")


def test_fails_on_an_embedding_model_mismatch_and_suggests_recreate(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    other_model = f"projects/{PROJECT}/locations/{LOCATION}/publishers/google/models/other"
    fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, other_model)

    # Act / Assert
    with pytest.raises(SyncError, match="--recreate"):
        run_sync(fake_rag_client, fake_clock)


def test_recreate_deletes_files_then_the_corpus_then_creates_a_new_one(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    old = fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, ENDPOINT)
    fake_rag_client.add_file(old, name_of("gdpr"))
    fake_rag_client.add_file(old, name_of("hipaa"))

    # Act
    run_sync(fake_rag_client, fake_clock, recreate=True)

    # Assert
    destructive = fake_rag_client.calls_named("delete_file", "delete_corpus", "create_corpus")
    order = [call[0] for call in destructive]
    assert order[:4] == ["delete_file", "delete_file", "delete_corpus", "create_corpus"]
    assert [corpus.name for corpus in fake_rag_client.corpora] != [old.name]
    assert len(fake_rag_client.corpora) == 1


def test_uploads_every_missing_document(fake_rag_client: FakeRagClient, fake_clock: FakeClock):
    # Arrange / Act
    result = run_sync(fake_rag_client, fake_clock)

    # Assert
    uploaded = [call[1] for call in fake_rag_client.calls_named("upload_file")]
    assert sorted(uploaded) == sorted(name_of(doc_id) for doc_id in DOC_IDS)
    assert {outcome.action for outcome in result.outcomes} == {"upload"}


def test_a_second_run_with_unchanged_documents_uploads_nothing(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    run_sync(fake_rag_client, fake_clock)
    uploads_after_first_run = len(fake_rag_client.calls_named("upload_file"))

    # Act
    result = run_sync(fake_rag_client, fake_clock)

    # Assert
    assert len(fake_rag_client.calls_named("upload_file")) == uploads_after_first_run
    assert not fake_rag_client.calls_named("delete_file")
    assert [outcome.action for outcome in result.outcomes] == ["skip"] * 5


def test_a_changed_document_uploads_first_and_deletes_the_old_file_after_it_is_active(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    corpus = fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, ENDPOINT)
    for doc_id in DOC_IDS:
        fake_rag_client.add_file(corpus, name_of(doc_id, "b"))
    stale = next(
        f for f in fake_rag_client.files[corpus.name] if f.display_name == name_of("gdpr", "b")
    )
    fake_rag_client.polls_before_active = 2
    changed = [LocalDocument("gdpr", Path("build/corpus/gdpr.md"), "a" * 12)]
    unchanged = [
        LocalDocument(doc_id, Path(f"build/corpus/{doc_id}.md"), "b" * 12) for doc_id in DOC_IDS[1:]
    ]

    # Act
    result = run_sync(fake_rag_client, fake_clock, docs=changed + unchanged)

    # Assert
    kinds = [call[0] for call in fake_rag_client.calls]
    upload_index = kinds.index("upload_file")
    delete_index = kinds.index("delete_file")
    assert upload_index < delete_index
    assert "get_file" in kinds[upload_index:delete_index]
    assert fake_rag_client.calls_named("delete_file") == [("delete_file", stale.name)]
    assert next(o for o in result.outcomes if o.doc_id == "gdpr").action == "replace"


def test_cleans_duplicates_left_by_an_interrupted_run(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    corpus = fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, ENDPOINT)
    for doc_id in DOC_IDS:
        fake_rag_client.add_file(corpus, name_of(doc_id))
    old = fake_rag_client.add_file(corpus, name_of("gdpr", "b"))

    # Act
    result = run_sync(fake_rag_client, fake_clock)

    # Assert
    assert not fake_rag_client.calls_named("upload_file")
    assert fake_rag_client.calls_named("delete_file") == [("delete_file", old.name)]
    assert next(o for o in result.outcomes if o.doc_id == "gdpr").action == "repair"


def test_waits_for_a_file_an_interrupted_run_left_processing_instead_of_uploading_again(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    corpus = fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, ENDPOINT)
    for doc_id in DOC_IDS[1:]:
        fake_rag_client.add_file(corpus, name_of(doc_id))
    fake_rag_client.add_file(corpus, name_of("gdpr"), state="PENDING")

    # Act
    result = run_sync(fake_rag_client, fake_clock)

    # Assert
    assert not fake_rag_client.calls_named("upload_file")
    assert next(o for o in result.outcomes if o.doc_id == "gdpr").action == "upload"


def test_deletes_a_file_found_in_error_and_uploads_it_again(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    corpus = fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, ENDPOINT)
    for doc_id in DOC_IDS[1:]:
        fake_rag_client.add_file(corpus, name_of(doc_id))
    failed = fake_rag_client.add_file(corpus, name_of("gdpr"), state="ERROR")

    # Act
    run_sync(fake_rag_client, fake_clock)

    # Assert
    kinds = [call[0] for call in fake_rag_client.calls_named("delete_file", "upload_file")]
    assert kinds == ["delete_file", "upload_file"]
    assert fake_rag_client.calls_named("delete_file") == [("delete_file", failed.name)]


def test_retries_one_error_file_once_then_fails_with_its_status(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    fake_rag_client.upload_states = ["ERROR", "ERROR"]

    # Act / Assert
    with pytest.raises(SyncError) as error:
        run_sync(fake_rag_client, fake_clock)
    assert "ERROR" in str(error.value)
    assert name_of("gdpr") in str(error.value)
    assert len(fake_rag_client.calls_named("upload_file")) == 2
    assert len(fake_rag_client.calls_named("delete_file")) == 1


def test_recovers_when_the_retry_after_an_error_succeeds(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    fake_rag_client.upload_states = ["ERROR"]

    # Act
    result = run_sync(fake_rag_client, fake_clock)

    # Assert
    assert len(fake_rag_client.calls_named("upload_file")) == 6
    assert len(fake_rag_client.calls_named("delete_file")) == 1
    assert {outcome.action for outcome in result.outcomes} == {"upload"}


def test_times_out_waiting_for_active_and_names_the_file(
    fake_rag_client: FakeRagClient, fake_clock: FakeClock
):
    # Arrange
    fake_rag_client.polls_before_active = None

    # Act / Assert
    with pytest.raises(SyncError, match=r"gdpr__a{12}\.md") as error:
        run_sync(fake_rag_client, fake_clock)
    assert "10 minutes" in str(error.value)
    assert fake_clock.now >= 600


def test_reports_stray_files_and_leaves_them(fake_rag_client: FakeRagClient, fake_clock: FakeClock):
    # Arrange
    corpus = fake_rag_client.add_corpus(CORPUS_DISPLAY_NAME, ENDPOINT)
    stray = fake_rag_client.add_file(corpus, "scratch-notes.txt")

    # Act
    result = run_sync(fake_rag_client, fake_clock)

    # Assert
    assert [file.display_name for file in result.strays] == ["scratch-notes.txt"]
    assert stray.name not in [call[1] for call in fake_rag_client.calls_named("delete_file")]


def test_plans_an_upload_a_skip_and_a_stray_from_the_remote_listing():
    # Arrange
    remote = [
        RemoteFile("files/1", name_of("gdpr"), "ACTIVE"),
        RemoteFile("files/2", "mystery.pdf", "ACTIVE"),
    ]
    docs = [local_docs()[0], local_docs()[1]]

    # Act
    plan = plan_file_actions(remote, docs)

    # Assert
    assert [(a.doc_id, a.kind) for a in plan.actions] == [
        ("gdpr", ActionKind.SKIP),
        ("hipaa", ActionKind.UPLOAD),
    ]
    assert [file.display_name for file in plan.strays] == ["mystery.pdf"]


def test_content_hash_changes_when_the_chunk_settings_change():
    # Arrange
    markdown = "### GDPR > Art. 1\nCite as: GDPR Art. 1(1)\n"

    # Act
    baseline = content_hash(markdown)
    other_chunk_size = content_hash(markdown, chunk_size=CHUNK_SIZE // 2)
    other_overlap = content_hash(markdown, chunk_overlap=CHUNK_OVERLAP + 1)
    other_text = content_hash(markdown + "x")

    # Assert
    assert len(baseline) == 12
    assert baseline == content_hash(markdown)
    assert len({baseline, other_chunk_size, other_overlap, other_text}) == 4


def test_the_upload_config_asks_for_fixed_length_chunks_of_1024_with_200_overlap():
    # Arrange / Act
    config = build_upload_config()

    # Assert
    chunking = config.rag_file_transformation_config.rag_file_chunking_config
    assert chunking.fixed_length_chunking.chunk_size == 1024
    assert chunking.fixed_length_chunking.chunk_overlap == 200


def test_the_corpus_spec_names_the_embedding_endpoint():
    # Arrange / Act
    spec = build_corpus_spec("policypulse-5docs-corpus", "A description.", ENDPOINT)

    # Assert
    endpoint = spec.vector_db_config.rag_embedding_model_config.vertex_prediction_endpoint
    assert spec.display_name == "policypulse-5docs-corpus"
    assert endpoint.endpoint == ENDPOINT


# The adapter's only collaborator is `agentplatform.Client(...).rag`. FakeSdkRag stands in for that
# one object and returns real SDK model objects, so the mapping runs against the SDK's own types.

CORPUS_NAME = "projects/demo-project/locations/us-east4/ragCorpora/7"
FILE_NAME = f"{CORPUS_NAME}/ragFiles/9"
EMBEDDING_FIELDS = ("vector_db_config", "rag_vector_db_config", "rag_embedding_model_config")


class FakeSdkRag:
    """The `rag` object of `agentplatform.Client`, with the SDK's keyword-only method signatures.

    List responses are served by page token, so a listing that forgets to pass the token fails on
    the lookup. `corpus` and `file` are what the single-resource methods return.
    """

    def __init__(self) -> None:
        self.client_args: dict[str, str] = {}
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.corpus_pages: dict[str | None, sdk.ListRagCorporaResponse] = {}
        self.file_pages: dict[tuple[str, str | None], sdk.ListRagFilesResponse] = {}
        self.corpus = sdk.RagCorpus()
        self.file = sdk.RagFile()

    def requests_named(self, kind: str) -> list[dict[str, Any]]:
        return [kwargs for name, kwargs in self.requests if name == kind]

    def list_corpora(self, *, config: sdk.ListRagCorporaConfig | None = None):
        self.requests.append(("list_corpora", {"config": config}))
        return self.corpus_pages[config.page_token if config else None]

    def create_corpus(self, *, rag_corpus: sdk.RagCorpus, config: Any = None):
        self.requests.append(("create_corpus", {"rag_corpus": rag_corpus}))
        return self.corpus

    def get_corpus(self, *, name: str, config: Any = None):
        self.requests.append(("get_corpus", {"name": name}))
        return self.corpus

    def delete_corpus(self, *, name: str, config: Any = None) -> None:
        self.requests.append(("delete_corpus", {"name": name}))

    def list_files(self, *, name: str, config: sdk.ListRagFilesConfig | None = None):
        self.requests.append(("list_files", {"name": name, "config": config}))
        return self.file_pages[(name, config.page_token if config else None)]

    def upload_file(
        self,
        *,
        corpus_name: str,
        path: str,
        display_name: str | None = None,
        upload_rag_file_config: sdk.UploadRagFileConfig | None = None,
        request_config: Any = None,
    ):
        self.requests.append(
            (
                "upload_file",
                {
                    "corpus_name": corpus_name,
                    "path": path,
                    "display_name": display_name,
                    "upload_rag_file_config": upload_rag_file_config,
                },
            )
        )
        return self.file

    def get_file(self, *, name: str, config: Any = None):
        self.requests.append(("get_file", {"name": name}))
        return self.file

    def delete_file(self, *, name: str, config: Any = None) -> None:
        self.requests.append(("delete_file", {"name": name}))


@pytest.fixture
def sdk_rag(monkeypatch: pytest.MonkeyPatch) -> FakeSdkRag:
    rag = FakeSdkRag()

    class FakeClient:
        def __init__(self, *, project: str, location: str) -> None:
            rag.client_args = {"project": project, "location": location}
            self.rag = rag

    monkeypatch.setattr(agentplatform, "Client", FakeClient)
    return rag


@pytest.fixture
def rag_client(sdk_rag: FakeSdkRag) -> AgentPlatformRagClient:
    return AgentPlatformRagClient(PROJECT, LOCATION)


def sdk_file(state: sdk.RagFileState | None, display_name: str | None = None) -> sdk.RagFile:
    return sdk.RagFile(
        name=FILE_NAME,
        display_name=display_name if display_name is not None else name_of("gdpr"),
        file_status=sdk.RagFileStatus(state=state),
    )


def embedding_config(endpoint: str | None) -> sdk.RagEmbeddingModelConfig:
    if endpoint is None:
        return sdk.RagEmbeddingModelConfig()
    return sdk.RagEmbeddingModelConfig(
        vertex_prediction_endpoint=sdk.RagEmbeddingModelConfigVertexPredictionEndpoint(
            endpoint=endpoint
        )
    )


def corpus_with_endpoint_in(
    field: str, endpoint: str | None, display_name: str = "c"
) -> sdk.RagCorpus:
    """A corpus whose embedding config sits under `field`, one of EMBEDDING_FIELDS."""
    config = embedding_config(endpoint)
    if field == "rag_embedding_model_config":
        return sdk.RagCorpus(
            name=CORPUS_NAME, display_name=display_name, rag_embedding_model_config=config
        )
    nested = sdk.RagVectorDbConfig(rag_embedding_model_config=config)
    return sdk.RagCorpus(name=CORPUS_NAME, display_name=display_name, **{field: nested})


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        pytest.param(sdk.RagFileState.ACTIVE, "ACTIVE", id="active"),
        pytest.param(sdk.RagFileState.ERROR, "ERROR", id="error"),
        pytest.param(sdk.RagFileState.STATE_UNSPECIFIED, "STATE_UNSPECIFIED", id="unspecified"),
    ],
)
def test_a_file_reports_its_sdk_state_by_name(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient, state: sdk.RagFileState, expected: str
):
    # Arrange
    sdk_rag.file = sdk_file(state)

    # Act
    remote = rag_client.get_file(FILE_NAME)

    # Assert
    assert remote == RemoteFile(FILE_NAME, name_of("gdpr"), expected)


def test_a_file_without_a_status_is_still_processing(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file = sdk.RagFile(name=FILE_NAME, display_name=name_of("gdpr"))

    # Act
    remote = rag_client.get_file(FILE_NAME)

    # Assert
    assert remote.state == "STATE_UNSPECIFIED"


def test_a_file_status_without_a_state_is_still_processing(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file = sdk_file(state=None)

    # Act
    remote = rag_client.get_file(FILE_NAME)

    # Assert
    assert remote.state == "STATE_UNSPECIFIED"


def test_a_file_without_a_display_name_maps_to_an_empty_one(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file = sdk.RagFile(name=FILE_NAME, file_status=sdk.RagFileStatus(state=None))

    # Act
    remote = rag_client.get_file(FILE_NAME)

    # Assert
    assert remote.display_name == ""


@pytest.mark.parametrize("field", EMBEDDING_FIELDS)
def test_a_corpus_reports_the_embedding_endpoint_from_whichever_field_holds_it(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient, field: str
):
    # Arrange
    sdk_rag.corpus = corpus_with_endpoint_in(field, ENDPOINT)

    # Act
    remote = rag_client.get_corpus(CORPUS_NAME)

    # Assert
    assert remote.embedding_endpoint == ENDPOINT


def test_a_corpus_with_no_embedding_config_has_no_endpoint(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus = sdk.RagCorpus(name=CORPUS_NAME, display_name="c")

    # Act
    remote = rag_client.get_corpus(CORPUS_NAME)

    # Assert
    assert remote.embedding_endpoint is None


def test_a_blank_embedding_endpoint_counts_as_missing(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus = corpus_with_endpoint_in("vector_db_config", "")

    # Act
    remote = rag_client.get_corpus(CORPUS_NAME)

    # Assert
    assert remote.embedding_endpoint is None


def test_the_endpoint_search_moves_past_a_field_that_names_no_endpoint(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus = sdk.RagCorpus(
        name=CORPUS_NAME,
        display_name="c",
        vector_db_config=sdk.RagVectorDbConfig(rag_embedding_model_config=embedding_config(None)),
        rag_vector_db_config=sdk.RagVectorDbConfig(
            rag_embedding_model_config=embedding_config(ENDPOINT)
        ),
    )

    # Act
    remote = rag_client.get_corpus(CORPUS_NAME)

    # Assert
    assert remote.embedding_endpoint == ENDPOINT


def test_vector_db_config_takes_precedence_when_two_fields_name_an_endpoint(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    preferred = f"{ENDPOINT}-preferred"
    sdk_rag.corpus = sdk.RagCorpus(
        name=CORPUS_NAME,
        display_name="c",
        vector_db_config=sdk.RagVectorDbConfig(
            rag_embedding_model_config=embedding_config(preferred)
        ),
        rag_embedding_model_config=embedding_config(ENDPOINT),
    )

    # Act
    remote = rag_client.get_corpus(CORPUS_NAME)

    # Assert
    assert remote.embedding_endpoint == preferred


def test_a_corpus_without_a_display_name_maps_to_an_empty_one(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus = sdk.RagCorpus(name=CORPUS_NAME)

    # Act
    remote = rag_client.get_corpus(CORPUS_NAME)

    # Assert
    assert remote == RemoteCorpus(CORPUS_NAME, "", None)


def test_list_corpora_collects_every_page_in_order(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus_pages = {
        None: sdk.ListRagCorporaResponse(
            rag_corpora=[sdk.RagCorpus(name="corpora/1", display_name="one")],
            next_page_token="page-2",
        ),
        "page-2": sdk.ListRagCorporaResponse(
            rag_corpora=[sdk.RagCorpus(name="corpora/2", display_name="two")],
            next_page_token="page-3",
        ),
        "page-3": sdk.ListRagCorporaResponse(
            rag_corpora=[sdk.RagCorpus(name="corpora/3", display_name="three")]
        ),
    }

    # Act
    corpora = rag_client.list_corpora()

    # Assert
    assert [corpus.name for corpus in corpora] == ["corpora/1", "corpora/2", "corpora/3"]


def test_list_corpora_returns_an_empty_list_when_the_service_has_none(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus_pages = {None: sdk.ListRagCorporaResponse()}

    # Act
    corpora = rag_client.list_corpora()

    # Assert
    assert corpora == []


def test_list_corpora_stops_at_an_empty_page_token(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus_pages = {
        None: sdk.ListRagCorporaResponse(
            rag_corpora=[sdk.RagCorpus(name="corpora/1", display_name="one")],
            next_page_token="",
        )
    }

    # Act
    corpora = rag_client.list_corpora()

    # Assert
    assert [corpus.name for corpus in corpora] == ["corpora/1"]


def test_list_files_collects_every_page_of_the_named_corpus(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file_pages = {
        (CORPUS_NAME, None): sdk.ListRagFilesResponse(
            rag_files=[sdk_file(sdk.RagFileState.ACTIVE, name_of("gdpr"))],
            next_page_token="page-2",
        ),
        (CORPUS_NAME, "page-2"): sdk.ListRagFilesResponse(
            rag_files=[sdk_file(sdk.RagFileState.ERROR, name_of("hipaa"))]
        ),
    }

    # Act
    files = rag_client.list_files(CORPUS_NAME)

    # Assert
    assert [(f.display_name, f.state) for f in files] == [
        (name_of("gdpr"), "ACTIVE"),
        (name_of("hipaa"), "ERROR"),
    ]


def test_list_files_returns_an_empty_list_for_an_empty_corpus(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file_pages = {(CORPUS_NAME, None): sdk.ListRagFilesResponse()}

    # Act
    files = rag_client.list_files(CORPUS_NAME)

    # Assert
    assert files == []


def test_list_files_stops_at_an_empty_page_token(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file_pages = {
        (CORPUS_NAME, None): sdk.ListRagFilesResponse(
            rag_files=[sdk_file(sdk.RagFileState.ACTIVE)], next_page_token=""
        )
    }

    # Act
    files = rag_client.list_files(CORPUS_NAME)

    # Assert
    assert len(files) == 1


def test_create_corpus_sends_the_description_and_embedding_endpoint_in_the_spec(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus = corpus_with_endpoint_in("vector_db_config", ENDPOINT)

    # Act
    rag_client.create_corpus(CORPUS_DISPLAY_NAME, "A description.", ENDPOINT)

    # Assert
    (request,) = sdk_rag.requests_named("create_corpus")
    spec = request["rag_corpus"]
    endpoint = spec.vector_db_config.rag_embedding_model_config.vertex_prediction_endpoint
    assert (spec.display_name, spec.description) == (CORPUS_DISPLAY_NAME, "A description.")
    assert endpoint.endpoint == ENDPOINT


def test_create_corpus_returns_the_corpus_the_service_created(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus = corpus_with_endpoint_in("vector_db_config", ENDPOINT, CORPUS_DISPLAY_NAME)

    # Act
    created = rag_client.create_corpus(CORPUS_DISPLAY_NAME, "A description.", ENDPOINT)

    # Assert
    assert created == RemoteCorpus(CORPUS_NAME, CORPUS_DISPLAY_NAME, ENDPOINT)


def test_get_corpus_asks_for_the_corpus_by_name(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.corpus = sdk.RagCorpus(name=CORPUS_NAME, display_name="c")

    # Act
    rag_client.get_corpus(CORPUS_NAME)

    # Assert
    assert [r["name"] for r in sdk_rag.requests_named("get_corpus")] == [CORPUS_NAME]


def test_delete_corpus_asks_for_the_corpus_by_name(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Act
    rag_client.delete_corpus(CORPUS_NAME)

    # Assert
    assert [r["name"] for r in sdk_rag.requests_named("delete_corpus")] == [CORPUS_NAME]


def test_get_file_asks_for_the_file_by_name(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file = sdk_file(sdk.RagFileState.ACTIVE)

    # Act
    rag_client.get_file(FILE_NAME)

    # Assert
    assert [r["name"] for r in sdk_rag.requests_named("get_file")] == [FILE_NAME]


def test_delete_file_asks_for_the_file_by_name(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Act
    rag_client.delete_file(FILE_NAME)

    # Assert
    assert [r["name"] for r in sdk_rag.requests_named("delete_file")] == [FILE_NAME]


def test_upload_file_sends_the_corpus_the_path_as_text_and_the_display_name(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file = sdk_file(sdk.RagFileState.ACTIVE)
    path = Path("build/corpus/gdpr.md")

    # Act
    rag_client.upload_file(CORPUS_NAME, path, name_of("gdpr"))

    # Assert
    (request,) = sdk_rag.requests_named("upload_file")
    assert request["corpus_name"] == CORPUS_NAME
    assert request["path"] == str(path)
    assert request["display_name"] == name_of("gdpr")


def test_upload_file_asks_for_the_fixed_length_chunking_settings(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file = sdk_file(sdk.RagFileState.ACTIVE)

    # Act
    rag_client.upload_file(CORPUS_NAME, Path("build/corpus/gdpr.md"), name_of("gdpr"))

    # Assert
    (request,) = sdk_rag.requests_named("upload_file")
    config = request["upload_rag_file_config"].rag_file_transformation_config
    chunking = config.rag_file_chunking_config.fixed_length_chunking
    assert (chunking.chunk_size, chunking.chunk_overlap) == (CHUNK_SIZE, CHUNK_OVERLAP)


def test_upload_file_returns_the_file_the_service_stored_with_its_state(
    sdk_rag: FakeSdkRag, rag_client: AgentPlatformRagClient
):
    # Arrange
    sdk_rag.file = sdk_file(sdk.RagFileState.ERROR)

    # Act
    uploaded = rag_client.upload_file(CORPUS_NAME, Path("build/corpus/gdpr.md"), name_of("gdpr"))

    # Assert
    assert uploaded == RemoteFile(FILE_NAME, name_of("gdpr"), "ERROR")


def test_the_sdk_client_is_created_for_the_given_project_and_location(sdk_rag: FakeSdkRag):
    # Act
    AgentPlatformRagClient("another-project", "europe-west4")

    # Assert
    assert sdk_rag.client_args == {"project": "another-project", "location": "europe-west4"}


def test_creating_the_client_registers_markdown_as_a_mime_type(
    sdk_rag: FakeSdkRag, monkeypatch: pytest.MonkeyPatch
):
    # Arrange
    monkeypatch.delitem(mimetypes.types_map, ".md", raising=False)
    assert mimetypes.guess_type("gdpr.md")[0] != "text/markdown"

    # Act
    AgentPlatformRagClient(PROJECT, LOCATION)

    # Assert
    assert mimetypes.guess_type("gdpr.md")[0] == "text/markdown"
