import importlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.tools.retrieval.vertex_ai_rag_retrieval import VertexAiRagRetrieval
from google.genai import types

EVALSET_PATH = Path(__file__).resolve().parents[2] / "eval" / "policypulse_evalset.json"
CORPUS = "projects/demo/locations/us-east4/ragCorpora/42"


@pytest.fixture
def reload_agent(monkeypatch: pytest.MonkeyPatch) -> Callable[[], ModuleType]:
    """Reload the agent module so it re-reads the environment, then restore it afterwards."""

    def reload() -> ModuleType:
        return importlib.reload(importlib.import_module("policypulse_rag.agent"))

    yield reload
    monkeypatch.undo()
    reload()


@pytest.fixture
def agent_module() -> ModuleType:
    return importlib.import_module("policypulse_rag.agent")


@pytest.fixture
def root_agent(agent_module: ModuleType) -> LlmAgent:
    return agent_module.build_root_agent(rag_corpus=CORPUS, model="gemini-2.5-flash")


async def declared_tools(tool: object, model: str = "gemini-2.5-flash") -> list[types.Tool]:
    request = LlmRequest(model=model)
    # BaseTool.process_llm_request does not read the tool context.
    await tool.process_llm_request(tool_context=None, llm_request=request)
    return list(request.config.tools or [])


def test_the_root_agent_is_named_policypulse_rag_and_defaults_to_gemini_2_5_flash(
    reload_agent: Callable[[], ModuleType], monkeypatch: pytest.MonkeyPatch
):
    # Arrange
    monkeypatch.delenv("POLICYPULSE_MODEL", raising=False)

    # Act
    module = reload_agent()

    # Assert
    assert module.root_agent.name == "policypulse_rag"
    assert module.root_agent.model == "gemini-2.5-flash"


def test_the_model_comes_from_policypulse_model(
    reload_agent: Callable[[], ModuleType], monkeypatch: pytest.MonkeyPatch
):
    # Arrange
    monkeypatch.setenv("POLICYPULSE_MODEL", "gemini-2.5-pro")

    # Act
    module = reload_agent()

    # Assert
    assert module.root_agent.model == "gemini-2.5-pro"


def test_the_agent_has_one_tool_named_for_the_retrieval_the_eval_set_expects(root_agent: LlmAgent):
    # Arrange
    evalset = json.loads(EVALSET_PATH.read_text(encoding="utf-8"))
    expected_names = {
        use["name"]
        for case in evalset["eval_cases"]
        for use in case["conversation"][0]["intermediate_data"]["tool_uses"]
    }

    # Act
    tool_names = [tool.name for tool in root_agent.tools]

    # Assert
    assert tool_names == ["search_policy_documents"]
    assert set(tool_names) == expected_names


def test_the_tool_targets_the_corpus_with_top_k_10_and_threshold_0_6(root_agent: LlmAgent):
    # Arrange / Act
    store = root_agent.tools[0].vertex_rag_store

    # Assert
    assert [resource.rag_corpus for resource in store.rag_resources] == [CORPUS]
    assert store.similarity_top_k == 10
    assert store.vector_distance_threshold == 0.6


def test_the_corpus_comes_from_the_environment(
    reload_agent: Callable[[], ModuleType], monkeypatch: pytest.MonkeyPatch
):
    # Arrange
    monkeypatch.setenv("RAG_CORPUS_RESOURCE_NAME", CORPUS)

    # Act
    module = reload_agent()

    # Assert
    assert module.root_agent.tools[0].vertex_rag_store.rag_resources[0].rag_corpus == CORPUS


async def test_the_tool_is_declared_to_gemini_as_a_function(root_agent: LlmAgent):
    # Arrange / Act
    tools = await declared_tools(root_agent.tools[0])

    # Assert
    declarations = [d for tool in tools for d in (tool.function_declarations or [])]
    assert [declaration.name for declaration in declarations] == ["search_policy_documents"]
    assert all(tool.retrieval is None for tool in tools)


async def test_the_stock_retrieval_tool_attaches_server_side_retrieval_for_gemini():
    # Arrange: characterization of the parent class. When an ADK upgrade breaks this test,
    # check whether the PolicyDocsRetrieval override is still needed.
    stock = VertexAiRagRetrieval(
        name="search_policy_documents",
        description="Searches the reference documents.",
        rag_resources=[types.VertexRagStoreRagResource(rag_corpus=CORPUS)],
    )

    # Act
    tools = await declared_tools(stock)

    # Assert
    assert [tool.retrieval is not None for tool in tools] == [True]
    assert not any(tool.function_declarations for tool in tools)


def test_a_missing_corpus_name_raises_with_the_ingest_command(
    reload_agent: Callable[[], ModuleType], monkeypatch: pytest.MonkeyPatch
):
    # Arrange
    monkeypatch.delenv("RAG_CORPUS_RESOURCE_NAME", raising=False)

    # Act / Assert
    with pytest.raises(RuntimeError, match=r"python scripts/ingest_corpus\.py"):
        reload_agent()
    assert "RAG_CORPUS_RESOURCE_NAME" not in os.environ


def test_the_agent_answers_with_temperature_zero(root_agent: LlmAgent):
    # Arrange / Act
    config = root_agent.generate_content_config

    # Assert
    assert config.temperature == 0.0


def test_the_agent_uses_the_policypulse_instruction(root_agent: LlmAgent):
    # Arrange
    from policypulse_rag.prompts import INSTRUCTION

    # Act / Assert
    assert root_agent.instruction == INSTRUCTION
