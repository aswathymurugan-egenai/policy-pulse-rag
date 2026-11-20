import os
from collections.abc import Callable
from pathlib import Path

import pytest

from policypulse_ingest.corpus_sync import RemoteCorpus, RemoteFile

# The agent module reads the corpus name when it is imported, so the unit tests give it a
# placeholder. Tests that check the missing-value behavior remove it with monkeypatch.
os.environ.setdefault(
    "RAG_CORPUS_RESOURCE_NAME", "projects/unit-test/locations/us-east4/ragCorpora/0"
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
PAGE_BREAK = "=====PAGE BREAK====="


@pytest.fixture
def load_fixture_pages() -> Callable[[str], list[str]]:
    """Return a loader that splits a fixture file into page texts on the page-break marker."""

    def load(name: str) -> list[str]:
        raw = (FIXTURES_DIR / name).read_text(encoding="utf-8")
        return [page.strip("\n") for page in raw.split(PAGE_BREAK)]

    return load


class FakeClock:
    """A clock whose sleep advances time instantly, so polling tests run in no real time."""

    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


class FakeRagClient:
    """An in-memory RagClient. It fakes the network boundary and nothing else.

    `upload_states` holds the state each successive upload lands in; once it is empty uploads are
    ACTIVE. `polls_before_active` makes an uploaded file report PENDING for that many get_file
    calls, and None keeps it PENDING forever.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.corpora: list[RemoteCorpus] = []
        self.files: dict[str, list[RemoteFile]] = {}
        self.upload_states: list[str] = []
        self.polls_before_active: int | None = 0
        self._pending_polls: dict[str, int | None] = {}
        self._next_id = 1

    def add_corpus(self, display_name: str, endpoint: str) -> RemoteCorpus:
        corpus = RemoteCorpus(self._new_name("ragCorpora"), display_name, endpoint)
        self.corpora.append(corpus)
        self.files[corpus.name] = []
        return corpus

    def add_file(
        self, corpus: RemoteCorpus, display_name: str, state: str = "ACTIVE"
    ) -> RemoteFile:
        remote = RemoteFile(self._new_name("ragFiles"), display_name, state)
        self.files[corpus.name].append(remote)
        return remote

    def calls_named(self, *kinds: str) -> list[tuple[str, ...]]:
        return [call for call in self.calls if call[0] in kinds]

    def list_corpora(self) -> list[RemoteCorpus]:
        self.calls.append(("list_corpora",))
        return list(self.corpora)

    def create_corpus(
        self, display_name: str, description: str, embedding_endpoint: str
    ) -> RemoteCorpus:
        self.calls.append(("create_corpus", display_name, embedding_endpoint))
        return self.add_corpus(display_name, embedding_endpoint)

    def get_corpus(self, name: str) -> RemoteCorpus:
        self.calls.append(("get_corpus", name))
        return next(corpus for corpus in self.corpora if corpus.name == name)

    def delete_corpus(self, name: str) -> None:
        self.calls.append(("delete_corpus", name))
        self.corpora = [corpus for corpus in self.corpora if corpus.name != name]
        self.files.pop(name, None)

    def list_files(self, corpus_name: str) -> list[RemoteFile]:
        self.calls.append(("list_files", corpus_name))
        return list(self.files[corpus_name])

    def upload_file(self, corpus_name: str, path: Path, display_name: str) -> RemoteFile:
        self.calls.append(("upload_file", display_name))
        state = self.upload_states.pop(0) if self.upload_states else "ACTIVE"
        if state == "ACTIVE" and self.polls_before_active != 0:
            state = "PENDING"
        remote = RemoteFile(self._new_name("ragFiles"), display_name, state)
        self.files[corpus_name].append(remote)
        self._pending_polls[remote.name] = self.polls_before_active
        return remote

    def get_file(self, name: str) -> RemoteFile:
        self.calls.append(("get_file", name))
        for corpus_files in self.files.values():
            for index, remote in enumerate(corpus_files):
                if remote.name == name:
                    return self._advance(corpus_files, index, remote)
        raise KeyError(name)

    def delete_file(self, name: str) -> None:
        self.calls.append(("delete_file", name))
        for corpus_files in self.files.values():
            corpus_files[:] = [remote for remote in corpus_files if remote.name != name]

    def _advance(
        self, corpus_files: list[RemoteFile], index: int, remote: RemoteFile
    ) -> RemoteFile:
        remaining = self._pending_polls.get(remote.name, 0)
        if remote.state != "PENDING" or remaining is None:
            return remote
        if remaining > 0:
            self._pending_polls[remote.name] = remaining - 1
            return remote
        activated = RemoteFile(remote.name, remote.display_name, "ACTIVE")
        corpus_files[index] = activated
        return activated

    def _new_name(self, kind: str) -> str:
        name = f"projects/p/locations/l/ragCorpora/{self._next_id}"
        if kind == "ragFiles":
            name += f"/ragFiles/{self._next_id}"
        self._next_id += 1
        return name


@pytest.fixture
def fake_rag_client() -> FakeRagClient:
    return FakeRagClient()
