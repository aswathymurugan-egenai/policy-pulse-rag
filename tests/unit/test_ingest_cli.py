from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from policypulse_ingest.blocks import Block
from policypulse_ingest.cli import main
from policypulse_ingest.corpus_sync import CORPUS_DISPLAY_NAME, expected_embedding_endpoint
from policypulse_ingest.documents import SourceDocument

if TYPE_CHECKING:
    from conftest import FakeRagClient

DOC_IDS = ("alpha", "beta", "gamma", "delta", "epsilon")
PROJECT = "demo-project"
LOCATION = "us-east4"


def make_document(doc_id: str) -> SourceDocument:
    def split(pages: list[str]) -> list[Block]:
        return [Block(doc_id, f"{doc_id} Sec. 1", (doc_id, "Section 1"), "".join(pages).strip())]

    return SourceDocument(
        doc_id=doc_id,
        citation_name=doc_id,
        file_names=(f"{doc_id}.md",),
        label_pattern=re.compile(rf"^{doc_id} Sec\. \d+$"),
        split=split,
        required_labels=(f"{doc_id} Sec. 1",),
        block_count_range=(1, 5),
    )


DOCUMENTS = tuple(make_document(doc_id) for doc_id in DOC_IDS)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    for doc_id in DOC_IDS:
        (docs / f"{doc_id}.md").write_text(f"Text of {doc_id}.", encoding="utf-8")
    return tmp_path


def run(workspace: Path, *extra: str, environ: dict[str, str] | None = None, client=None):
    def forbidden_client(project: str, location: str):
        raise AssertionError("render-only and failed runs must not build a RAG client")

    argv = [
        "--docs-dir", str(workspace / "docs"),
        "--env-file", str(workspace / ".env"),
        "--build-dir", str(workspace / "build"),
        *extra,
    ]  # fmt: skip
    return main(
        argv,
        documents=DOCUMENTS,
        client_factory=(lambda project, location: client) if client else forbidden_client,
        environ=environ if environ is not None else {},
    )


def test_render_only_writes_five_markdown_files_and_never_builds_a_client(workspace: Path):
    # Arrange / Act
    exit_code = run(workspace, "--render-only")

    # Assert
    rendered = sorted(path.name for path in (workspace / "build" / "corpus").iterdir())
    assert exit_code == 0
    assert rendered == sorted(f"{doc_id}.md" for doc_id in DOC_IDS)
    assert "Cite as: alpha Sec. 1" in (workspace / "build" / "corpus" / "alpha.md").read_text()


def test_a_missing_google_cloud_project_exits_2_with_a_message(
    workspace: Path, capsys: pytest.CaptureFixture[str]
):
    # Arrange / Act
    exit_code = run(workspace, environ={})

    # Assert
    assert exit_code == 2
    assert "GOOGLE_CLOUD_PROJECT" in capsys.readouterr().err


def test_missing_source_files_exit_2_and_list_them(
    workspace: Path, capsys: pytest.CaptureFixture[str]
):
    # Arrange
    (workspace / "docs" / "beta.md").unlink()
    (workspace / "docs" / "delta.md").unlink()

    # Act
    exit_code = run(workspace, "--render-only")

    # Assert
    error = capsys.readouterr().err
    assert exit_code == 2
    assert "beta.md" in error
    assert "delta.md" in error


def test_a_successful_sync_writes_the_corpus_name_to_the_env_file(
    workspace: Path, fake_rag_client: FakeRagClient
):
    # Arrange
    environ = {"GOOGLE_CLOUD_PROJECT": PROJECT, "RAG_LOCATION": LOCATION}

    # Act
    exit_code = run(workspace, environ=environ, client=fake_rag_client)

    # Assert
    corpus = fake_rag_client.corpora[0]
    assert exit_code == 0
    assert corpus.display_name == CORPUS_DISPLAY_NAME
    assert (workspace / ".env").read_text() == f"RAG_CORPUS_RESOURCE_NAME={corpus.name}\n"
    assert len(fake_rag_client.calls_named("upload_file")) == 5


def test_a_second_run_prints_five_skip_lines_and_leaves_the_env_file_unchanged(
    workspace: Path, fake_rag_client: FakeRagClient, capsys: pytest.CaptureFixture[str]
):
    # Arrange
    environ = {"GOOGLE_CLOUD_PROJECT": PROJECT, "RAG_LOCATION": LOCATION}
    run(workspace, environ=environ, client=fake_rag_client)
    env_after_first_run = (workspace / ".env").read_bytes()
    capsys.readouterr()

    # Act
    exit_code = run(workspace, environ=environ, client=fake_rag_client)

    # Assert
    output = capsys.readouterr().out
    assert exit_code == 0
    assert len(re.findall(r"^\s*\w+\s+skip\b", output, flags=re.MULTILINE)) == 5
    assert len(fake_rag_client.calls_named("upload_file")) == 5
    assert (workspace / ".env").read_bytes() == env_after_first_run


def test_the_rag_location_falls_back_to_the_google_cloud_location(
    workspace: Path, fake_rag_client: FakeRagClient
):
    # Arrange
    environ = {"GOOGLE_CLOUD_PROJECT": PROJECT, "GOOGLE_CLOUD_LOCATION": "europe-west4"}

    # Act
    exit_code = run(workspace, environ=environ, client=fake_rag_client)

    # Assert
    endpoint = expected_embedding_endpoint(PROJECT, "europe-west4")
    assert exit_code == 0
    assert fake_rag_client.calls_named("create_corpus")[0][2] == endpoint


def test_settings_come_from_the_env_file_when_the_environment_has_none(
    workspace: Path, fake_rag_client: FakeRagClient
):
    # Arrange
    (workspace / ".env").write_text(f"GOOGLE_CLOUD_PROJECT={PROJECT}\nRAG_LOCATION={LOCATION}\n")

    # Act
    exit_code = run(workspace, environ={}, client=fake_rag_client)

    # Assert
    assert exit_code == 0
    assert "RAG_CORPUS_RESOURCE_NAME=" in (workspace / ".env").read_text()
    assert f"GOOGLE_CLOUD_PROJECT={PROJECT}" in (workspace / ".env").read_text()


def test_a_contract_failure_exits_1_before_any_cloud_call(
    workspace: Path, capsys: pytest.CaptureFixture[str]
):
    # Arrange
    broken = tuple(
        SourceDocument(
            **{**document.__dict__, "required_labels": (f"{document.doc_id} Sec. 99",)}
        )
        for document in DOCUMENTS
    )
    environ = {"GOOGLE_CLOUD_PROJECT": PROJECT, "RAG_LOCATION": LOCATION}

    # Act
    exit_code = main(
        [
            "--docs-dir", str(workspace / "docs"),
            "--env-file", str(workspace / ".env"),
            "--build-dir", str(workspace / "build"),
        ],  # fmt: skip
        documents=broken,
        client_factory=lambda project, location: pytest.fail("no client before the gate passes"),
        environ=environ,
    )

    # Assert
    assert exit_code == 1
    assert "Sec. 99" in capsys.readouterr().err
