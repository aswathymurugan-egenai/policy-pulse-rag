"""Fixtures for the live retrieval tests, which need ADC and a populated corpus."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_TEST_CORPUS_PREFIX = "projects/unit-test/"


def _corpus_resource_name() -> str:
    import os

    load_dotenv(REPO_ROOT / ".env")
    return os.environ.get("RAG_CORPUS_RESOURCE_NAME", "").strip()


@pytest.fixture(scope="session")
def live_corpus_name() -> str:
    """The corpus resource name from the environment, or a skip when there is no live corpus."""
    name = _corpus_resource_name()
    if not name or name.startswith(UNIT_TEST_CORPUS_PREFIX):
        pytest.skip("RAG_CORPUS_RESOURCE_NAME is not set; run scripts/ingest_corpus.py first.")
    try:
        import google.auth

        google.auth.default()
    except Exception as error:  # any credential failure means there is no live access
        pytest.skip(f"Application Default Credentials are unavailable: {error}")
    return name


@pytest.fixture(scope="session")
def retrieve(live_corpus_name: str) -> Callable[[str], list[Any]]:
    """Return a function that retrieves contexts for a query with the agent's store settings."""
    import agentplatform
    from agentplatform import types
    from google.genai import types as genai_types

    from policypulse_rag.agent import SIMILARITY_TOP_K, VECTOR_DISTANCE_THRESHOLD

    _, project, _, location, *_ = live_corpus_name.split("/")
    client = agentplatform.Client(project=project, location=location)
    store = genai_types.VertexRagStore(
        rag_resources=[genai_types.VertexRagStoreRagResource(rag_corpus=live_corpus_name)],
        vector_distance_threshold=VECTOR_DISTANCE_THRESHOLD,
    )

    def retrieve_contexts(query: str) -> list[Any]:
        response = client.rag.retrieve_contexts(
            vertex_rag_store=store,
            query=types.RagQuery(text=query, similarity_top_k=SIMILARITY_TOP_K),
        )
        return list(response.contexts.contexts) if response.contexts else []

    return retrieve_contexts
