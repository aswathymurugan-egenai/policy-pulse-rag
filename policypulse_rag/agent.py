import os

from google.adk.agents import LlmAgent
from google.adk.tools.retrieval.vertex_ai_rag_retrieval import VertexAiRagRetrieval
from google.genai import types

from .prompts import INSTRUCTION

DEFAULT_MODEL = "gemini-2.5-flash"
RETRIEVAL_TOOL_NAME = "search_policy_documents"
SIMILARITY_TOP_K = 10
VECTOR_DISTANCE_THRESHOLD = 0.6


class PolicyDocsRetrieval(VertexAiRagRetrieval):
    """VertexAiRagRetrieval that Gemini calls as a function.

    On Gemini models the parent class attaches a server-side retrieval tool, which leaves no tool
    call in the event stream. Declaring a function lets the model choose its own queries, one per
    document for cross-document questions, and makes every search visible in adk web traces and
    adk eval trajectories.
    """

    async def process_llm_request(self, *, tool_context, llm_request) -> None:
        # Skip the parent's Gemini branch so BaseTool declares the function instead.
        await super(VertexAiRagRetrieval, self).process_llm_request(
            tool_context=tool_context, llm_request=llm_request
        )


def build_retrieval_tool(rag_corpus: str) -> PolicyDocsRetrieval:
    """The one search tool, bound to the corpus and the agreed retrieval settings."""
    return PolicyDocsRetrieval(
        name=RETRIEVAL_TOOL_NAME,
        description=(
            "Searches the five PolicyPulse reference documents (GDPR, HIPAA Privacy Rule "
            "Summary, NCSP 2013, Road Safety Policy, Registration API spec) and returns "
            "matching passages, each labeled with the citation to use."
        ),
        rag_resources=[types.VertexRagStoreRagResource(rag_corpus=rag_corpus)],
        similarity_top_k=SIMILARITY_TOP_K,
        vector_distance_threshold=VECTOR_DISTANCE_THRESHOLD,
    )


def build_root_agent(rag_corpus: str, model: str) -> LlmAgent:
    """The PolicyPulse agent for a corpus and a Gemini model."""
    return LlmAgent(
        name="policypulse_rag",
        model=model,
        description=(
            "Answers questions about five policy and specification documents with citations."
        ),
        instruction=INSTRUCTION,
        tools=[build_retrieval_tool(rag_corpus)],
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )


def _corpus_from_env() -> str:
    corpus = os.environ.get("RAG_CORPUS_RESOURCE_NAME", "").strip()
    if not corpus:
        raise RuntimeError(
            "RAG_CORPUS_RESOURCE_NAME is not set. Run `python scripts/ingest_corpus.py` "
            "to create the corpus and write its name to .env."
        )
    return corpus


root_agent = build_root_agent(
    rag_corpus=_corpus_from_env(),
    model=os.environ.get("POLICYPULSE_MODEL", DEFAULT_MODEL),
)
