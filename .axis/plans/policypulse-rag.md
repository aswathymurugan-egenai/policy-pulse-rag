# Plan: PolicyPulse RAG, a grounded Q&A agent on Google ADK and Vertex AI RAG Engine

**Slug:** `policypulse-rag` • **Created:** 2026-11-18 • **Produced against:** no commit (the repository has no `HEAD` yet; the working tree holds only AXIS scaffolding)

**Playbooks applied:** agentic-development, app-testing, data-pipelines, cloud-iam, core-repository

## Rationale

- **Problem:** Answer questions over five policy and specification documents with article-level citations and no general-knowledge fallback. The beneficiary is the reviewer who signs off. Their bar is a working `adk web` demo, an architecture diagram, and visible TDD.
- **Approaches considered:**
  1. Raw upload with tuned chunking (1024 tokens, 200 overlap). Least work. Article-level citations are unreliable for the 56,000-word GDPR, because most chunks do not carry their article number.
  2. **Breadcrumb preprocessing (chosen).** Extract text from each source, split it on that document's structural headers, prefix every section with a breadcrumb such as `GDPR > Article 33 > Notification of a personal data breach to the supervisory authority`, write markdown, and upload to one corpus `policypulse-5docs-corpus` with `text-embedding-005`, chunk size 1024 and overlap 200.
  3. One file per citation unit (about 270 GDPR files, display name equal to the citation). Non-obvious, slower to ingest, and harder to inspect.
- **Recommendation:** Breadcrumb preprocessing, with a unit-tested splitter per document. TDD runs as two loops. The first is fast mocked pytest unit tests, written first and run on every commit without GCP credentials. The second is the 13 acceptance Q&As, encoded in the eval set before the agent exists, red first and green by the end of the build. CI runs only the unit tests. The live `adk eval` runs manually and is the final gate.
- **Key tradeoff:** Per-document parsing rules to write and test, in exchange for citations that survive chunking.
- **Agreed defaults:** Gemini 2.5 Flash, with Pro as a one-line env switch. A RAG Engine region open to new projects, because us-central1 is allowlist-restricted for new projects. `similarity_top_k=10` and `vector_distance_threshold=0.6`, plus prompt rules for the Q13 refusal. The default `response_match_score` (ROUGE) penalizes correct paraphrased answers, so the eval adds rubric-judged criteria; Q12 and Q13 are the wording-sensitive cases.
- **Open questions:** The official download URLs for the four public PDFs. The file name and format of the user-supplied Customer Registration API spec.

## Objective

A reviewer runs `adk web`, asks any of the 13 acceptance questions, and gets an answer built only from retrieved passages, with inline citations such as `[GDPR Art. 33(1)]`; for Q13 the agent returns the refusal sentence. `adk eval` passes all 13 cases, the unit suite passes in CI without GCP credentials, and git history shows each test landing before its implementation.

## Context

- **Repository state (observed):** `AGENTS.md`, `CLAUDE.md`, `axis.json`, `.gitignore`, `.axis/`, `.claude/`. No commits, no `docs/`, no code.
- **Files involved:** `.gitignore:1-15` (AXIS-managed block; append below it), `AGENTS.md:1-101` (append a commands section), `.axis/context/glossary.md:15-17` (replace the TODO examples). Every other file in this plan is new and appears in the repository layout under the architecture section.
- **Constraints:**
  - Answers come only from `search_policy_documents` results, with zero general-knowledge fallback (user-provided).
  - Unit tests run with no GCP credentials and no network (user-provided).
  - The Customer Registration API spec belongs to a different system. This repo ingests a copy the user supplies and never edits it (user-provided).
  - No service-account key files anywhere. Local runs use Application Default Credentials (cloud-iam).
- **Dependencies:** the five source files in `docs/`; a GCP project with billing, `aiplatform.googleapis.com` enabled, and `roles/aiplatform.user` for the developer; Python 3.11 to 3.13 (the runbook uses 3.12).

### What was verified, and how

API claims were read from the published wheels: `google-adk` 2.14.1, `google-cloud-agentplatform` 2.10.0 and `google-cloud-aiplatform` 2.10.0, downloaded from PyPI on 2026-11-18 and inspected as source. The Vertex AI documentation pages could not be fetched in this session because WebFetch is denied by the session's permission mode. Service-side facts therefore stay UNVERIFIED, and each one has a preflight check in the runbook.

| Claim | Status | Evidence |
| --- | --- | --- |
| Latest `google-adk` is 2.14.1, released 2026-11-12 | VERIFIED | PyPI JSON |
| `VertexAiRagRetrieval(*, name, description, rag_corpora=None, rag_resources=None, similarity_top_k=None, vector_distance_threshold=None)` lives at `google.adk.tools.retrieval.vertex_ai_rag_retrieval` | VERIFIED | `tools/retrieval/vertex_ai_rag_retrieval.py` |
| `rag_resources` accepts `google.genai.types.VertexRagStoreRagResource`, a dict, or any object with `rag_corpus`/`rag_file_ids`, so `vertexai.rag.RagResource` still works | VERIFIED | `_to_rag_resource` in the same file |
| On any `gemini-*` model the tool attaches a server-side `types.Retrieval(vertex_rag_store=...)` and declares no function, so no tool call reaches the event stream or the eval trajectory | VERIFIED | `process_llm_request` in the same file; `is_gemini_model` in `utils/model_name_utils.py` |
| In function-call mode `run_async` calls `agentplatform.Client(...).aio.rag.retrieve_contexts` and returns only `context.text` per chunk, without the source file name | VERIFIED | `run_async` in the same file |
| The retrieval call takes project and region from the corpus resource name, so the RAG region can differ from the Gemini region | VERIFIED | `_project_and_location` in the same file |
| `run_async` needs `google-cloud-agentplatform`, which the `gcp` extra installs | VERIFIED | wheel `METADATA`; `missing_extra("google-cloud-agentplatform", "gcp")` |
| `vertexai.rag` and `vertexai.preview.rag` emit a deprecation warning pointing to `agentplatform.Client(...).rag` | VERIFIED | `vertexai/rag/__init__.py` in `google-cloud-aiplatform` 2.10.0 |
| `client.rag` offers `create_corpus`, `list_corpora`, `get_corpus`, `delete_corpus`, `upload_file`, `list_files`, `get_file`, `delete_file`, `retrieve_contexts`; list calls page with `page_token` and `next_page_token` | VERIFIED | `agentplatform/_genai/rag.py`, `agentplatform/_genai/types/common.py` |
| `upload_file` sets only `display_name` on the new file, and the per-file metadata config is documented as "Deprecated: Not in use" | VERIFIED | same files |
| The `upload_file` docstring example (`chunk_config=types.ChunkConfig(...)`) does not match the type; the real path is `rag_file_transformation_config.rag_file_chunking_config.fixed_length_chunking` | VERIFIED | `UploadRagFileConfig`, `RagFileChunkingConfig` |
| `delete_corpus` has no `force` option | VERIFIED | `DeleteRagCorpusConfig` |
| The retrieved-context `score` under COSINE_DISTANCE ranges from 0 to 2, and 0 is the most relevant | VERIFIED | `RagContextsContext.score` field description |
| The embedding endpoint field takes `projects/{project}/locations/{location}/publishers/google/models/text-embedding-005` | PARTIAL | field description observed; whether the short form is also accepted was not checked |
| Which corpus field the service honors: `vector_db_config`, `rag_vector_db_config` or `rag_embedding_model_config` | PARTIAL | all three serialize; the ingest reads the corpus back and prints the endpoint |
| Eval set schema: `EvalSet{eval_set_id, name, description, eval_cases}`, `EvalCase{eval_id, conversation, session_input, rubrics}`, `Invocation{invocation_id, user_content, final_response, intermediate_data{tool_uses, tool_responses, intermediate_responses}, rubrics}`; unknown keys are rejected | VERIFIED | `evaluation/eval_set.py`, `eval_case.py`, `common.py` (`extra="forbid"`) |
| Eval ids must match `^[a-zA-Z0-9_]+$` | VERIFIED | `local_eval_sets_manager._validate_id` |
| Criterion names include `tool_trajectory_avg_score`, `response_match_score` (ROUGE-1 F-measure), `final_response_match_v2`, `rubric_based_final_response_quality_v1`, `hallucinations_v1`, `rubric_based_tool_use_quality_v1`, `safety_v1`; the default config is trajectory 1.0 plus response match 0.8 | VERIFIED | `eval_metrics.py`, `eval_config.py`, `final_response_match_v1.py` |
| `ToolTrajectoryCriterion` supports `match_type` (EXACT, IN_ORDER, ANY_ORDER) and `ignore_args` | VERIFIED | `eval_metrics.py`, `trajectory_evaluator.py` |
| Case-level and invocation-level rubrics reach `rubric_based_final_response_quality_v1` only when their `type` is `FINAL_RESPONSE_QUALITY` | VERIFIED | `rubric_based_evaluator.create_effective_rubrics_list`, `RUBRIC_TYPE` |
| `adk eval AGENT_DIR EVAL_SET_FILE[:id,id] [--config_file_path] [--num_runs] [--parallelism] [--print_detailed_results]`; without `--config_file_path` it reads `test_config.json` next to the eval set | VERIFIED | `cli/cli_tools_click.py` |
| `multi_run_config.cross_run_criteria` accepts the built-in method `pass_rate` | VERIFIED | `eval_config.py`, `_multi_run_aggregation_methods.py` |
| ADK finds `.env` by walking up from the agent folder, so a repo-root `.env` serves both `adk web` and `adk eval` | VERIFIED | `cli/utils/envs.py` |
| `adk web` lists every top-level folder that holds an `__init__.py` as an agent; its default port is 8000 | VERIFIED | `cli/utils/agent_loader._looks_like_agent_dir`, `cli_web` |
| `GOOGLE_GENAI_USE_VERTEXAI` is deprecated in favor of `GOOGLE_GENAI_USE_ENTERPRISE`, and `adk create` writes `GOOGLE_GENAI_USE_ENTERPRISE=1` | VERIFIED | `utils/env_utils.py`, `cli/cli_create.py` |
| An instruction containing `{identifier}` is read as a session-state placeholder and raises `KeyError` when the key is missing | VERIFIED | `flows/llm_flows/prompt/_instructions_utils.py` |
| ADK's `LlmAgent` default model is `gemini-3.5-flash`; the eval judge default is `gemini-2.5-flash` | VERIFIED | `agents/llm_agent.py`, `JudgeModelOptions` |
| `gemini-2.5-flash` is still served on Vertex AI in the chosen region | UNVERIFIED | runbook preflight sends one request |
| RAG Engine regions open to new projects (candidate `us-east4`, fallback `europe-west4`) and the us-central1 restriction | UNVERIFIED (user-provided) | runbook preflight lists corpora in the region |
| Markdown (`.md`) is an accepted upload type, and chunk size counts tokens | UNVERIFIED | strong prior; the ingest can write `.txt` with the same content |
| The RAG-managed vector database may bill for a provisioned tier while it exists | UNVERIFIED | the SDK exposes `RagEngineConfig` tiers; pricing not checked |

### Playbook check

| Rule | How the plan meets it |
| --- | --- |
| Tools have a verb-noun name, one-sentence description, typed schema (agentic-development) | `search_policy_documents`, one-sentence description, ADK's `query: string` (required) schema |
| Every chunk carries provenance; ingest is idempotent and content-hash-guarded (agentic-development) | Breadcrumb plus `Cite as:` label in the chunk text; content hash in the file display name; unchanged files are skipped |
| Chunk on structure with overlap; calibrate on the eval set (agentic-development) | Per-document splitters; 1024/200 chunks; live recall@10 test calibrates the 0.6 threshold |
| Hybrid search with a reranker, or document the vector-only tradeoff (agentic-development) | Vector-only is recorded under Left unbuilt with the condition that would change it |
| Retrieval gated on recall and faithfulness (agentic-development) | Live recall@10 per question; `hallucinations_v1` in the eval. Precision@k is not measured (PARTIAL) |
| Write the failing test first; mock only at external boundaries; randomized order; property tests (app-testing) | Every step pairs a red test with its implementation; the only fakes are the RAG client (network) and pypdf output (file parsing); `pytest-randomly`; Hypothesis for the block renderer. Mutation testing and a coverage floor are deferred |
| Idempotent tasks, immutable raw layer, contract gate between layers (data-pipelines) | `docs/` is the raw layer, `build/corpus/` is derived, and a contract gate runs before upload |
| ADC only, no keys, least privilege, keyless CI (cloud-iam) | ADC user credentials; `roles/aiplatform.user`, the narrowest predefined role covering RAG Engine and Gemini, granted at project level; CI holds no cloud credential |
| One unit per top-level folder; root ignore file; nothing crosses a repo boundary except published artifacts (core-repository) | Layout below; `.gitignore` extended; the API spec copy is flagged as an open risk |

## Approach

**Chosen:** Breadcrumb preprocessing feeds one RAG corpus, and an `LlmAgent` reads it through `VertexAiRagRetrieval` declared to Gemini as a function.

- A small ingestion package extracts text from each source and splits it with a per-document splitter into citation blocks. It renders each block as markdown with a breadcrumb heading, a `Cite as:` line at the top and an `End of` line at the bottom.
- Blocks longer than 350 words split at sentence boundaries and repeat their labels. Every 1024-token chunk therefore contains at least one complete label, even when the chunk starts in the middle of a block.
- An idempotent sync uploads the five rendered files to `policypulse-5docs-corpus` and writes the corpus resource name to `.env`.
- The agent subclasses `VertexAiRagRetrieval` and overrides one method, so Gemini calls the tool as `search_policy_documents(query)`. The prompt tells the model to copy the `Cite as:` label after each claim.

**Planning finding that refines the shaping decision:** On Gemini models the stock tool attaches a server-side retrieval and declares no function (observed in 2.14.1). In that mode no tool call reaches the event stream, so the eval trajectory cannot see retrieval and the "always search first" rule cannot be checked. The model also cannot choose its own queries, which Q12 needs to reach four documents. The subclass keeps ADK's own retrieval code (`run_async`, which calls RAG Engine's RetrieveContexts) and makes every search visible in the `adk web` trace and in `adk eval` trajectories. Because `run_async` returns chunk text without the file name (observed), the in-text labels become the model's only provenance. That makes the breadcrumb design necessary.

**Alternative considered:** The stock `VertexAiRagRetrieval` in server-side mode. It needs no subclass and saves one model round trip per question. It lost on two counts: the reviewer's TDD bar needs an observable tool trajectory, and Q12 needs more than one retrieval per question.

**Reasoning:** The repo is greenfield, and the agentic-development playbook's Egen pick for Gemini on Vertex AI is ADK. A single agent with one read-only tool is the smallest design that meets the brief. Each per-document splitter is a pure function of text, so the hard part of the system (citations) is unit-testable without GCP. The function-call subclass is about ten lines and is pinned by a characterization test. If a future ADK release changes the parent's behavior, that test fails first.

**Left unbuilt:**

- **Hybrid search and a reranker.** Vector-only retrieval is accepted for five documents. Revisit if any acceptance question's expected label falls outside the top 10 in the live recall test.
- **Per-file metadata filters.** The SDK marks the upload metadata config "Not in use". Revisit if a question must be restricted to one document and prompt routing is not enough.
- **Forcing tool calls with `tool_config` mode ANY.** That mode forces a function call on every model turn, so the agent could never write its final answer. The prompt rule plus the trajectory criterion cover the requirement.
- **Live eval in CI.** It would need Workload Identity Federation into the project and a judge budget. Revisit once the agent changes weekly.
- **Parsing GDPR from the EUR-Lex HTML edition.** HTML carries more structure, but the brief fixes the PDF file names. Switch if the PDF splitter cannot pass its contract gate.
- **Deployment, session persistence beyond ADK's local SQLite, and a teardown command.** The runbook covers teardown through the console.

## 1. Architecture & Repository Layout

### Data flow

```
QUERY PATH (local)                                              GOOGLE CLOUD (Vertex AI)
==================                                              =======================
User (browser)
  | HTTP, localhost:8000
  v
adk web / Runner   (FastAPI; sessions in policypulse_rag/.adk/)
  | user message
  v
LlmAgent "policypulse_rag" -------- generateContent (ADC) -----> Gemini 2.5 Flash, or Pro via
  |  emits a function call, 1..n per question                    POLICYPULSE_MODEL
  |  search_policy_documents(query)                              (GOOGLE_CLOUD_LOCATION)
  v
VertexAiRagRetrieval  (PolicyDocsRetrieval subclass:
  |                    similarity_top_k=10, vector_distance_threshold=0.6)
  |---------------- RetrieveContexts (ADC) --------------------> Vertex AI RAG Engine (RAG_LOCATION)
  |                                                              corpus policypulse-5docs-corpus (5 docs)
  |<------- up to 10 chunk texts, each carrying Cite-as labels   text-embedding-005, 1024/200 chunks
  v
LlmAgent writes the answer from the returned chunks only
  |
  v
Grounded response with citations:  "... within 72 hours [GDPR Art. 33(1)]"
  or exactly: "The provided reference documents do not cover this topic."


INGESTION PATH (local CLI; safe to re-run)
==========================================
docs/  (5 source files, immutable raw layer)
  -> extract text            pypdf per page; markdown read as-is; running headers removed
  -> per-document splitter   citation blocks: label, breadcrumb, text, page
  -> render                  build/corpus/<doc_id>.md with "Cite as" / "End of" markers
  -> contract gate           expected labels present, block counts in range; fails before upload
  -> corpus sync             find or create the corpus, upload changed files (1024/200), wait for ACTIVE
  -> .env                    RAG_CORPUS_RESOURCE_NAME=projects/.../ragCorpora/...
```

### Repository layout

```
policy-pulse-rag/
├── README.md                     what it is, how to run, how to test, where the design lives
├── AGENTS.md                     existing; gains a Commands section
├── pyproject.toml                pinned dependencies; pytest and ruff config
├── .env.example                  every variable the agent and the ingest read
├── .gitignore                    existing AXIS block, plus .env, .venv/, build/, caches, policypulse_rag/.adk/
├── .github/workflows/ci.yml      lint and unit tests; no GCP credentials
│
├── policypulse_rag/              the ADK agent; the only top-level folder with an __init__.py
│   ├── __init__.py               from . import agent
│   ├── agent.py                  PolicyDocsRetrieval, build_root_agent(), root_agent
│   └── prompts.py                INSTRUCTION, REFUSAL_SENTENCE, CITATION_NAMES
│
├── scripts/                      no __init__.py, so adk web does not list it as an agent
│   ├── ingest_corpus.py          CLI entry point: --recreate, --render-only
│   └── policypulse_ingest/       the ingestion package
│       ├── __init__.py
│       ├── documents.py          five-document registry, source resolution, contract gate
│       ├── extract.py            pypdf page text, header/footer removal, line joining
│       ├── blocks.py             Block type, markdown renderer, long-block splitter
│       ├── splitters/
│       │   ├── __init__.py
│       │   ├── gdpr.py
│       │   ├── ncsp.py
│       │   ├── hipaa.py
│       │   ├── road_safety.py
│       │   └── registration_api.py
│       ├── corpus_sync.py        RagClient protocol, agentplatform adapter, sync planner and executor
│       ├── dotenv_file.py        idempotent RAG_CORPUS_RESOURCE_NAME upsert
│       └── cli.py                argument parsing and wiring
│
├── docs/                         the five source files plus SOURCES.md (publisher, URL, date, sha256)
├── eval/
│   ├── policypulse_evalset.json  the 13 acceptance cases
│   ├── test_config.json          criteria and thresholds; adk eval reads it by default
│   └── runs/                     committed summaries of each live eval run, the red-to-green record
├── tests/                        no __init__.py
│   ├── fixtures/                 short excerpts per document, plus a synthetic API spec
│   ├── unit/                     runs in CI
│   └── live/                     marked `live`; needs ADC and a populated corpus
└── build/                        gitignored render output (build/corpus/*.md)
```

The ingestion package lives under `scripts/` because `adk web` treats every top-level folder with an `__init__.py` as an agent (observed). A top-level `policypulse_ingest/` would appear in the agent picker and fail to load. Running `python scripts/ingest_corpus.py` puts `scripts/` on `sys.path`, and pytest reaches it through `pythonpath`.

## 2. Corpus Ingestion & Chunking Strategy (`scripts/ingest_corpus.py`)

### RAG Engine configuration

| Parameter | Value | Set in |
| --- | --- | --- |
| Corpus display name | `policypulse-5docs-corpus` | `corpus_sync.CORPUS_DISPLAY_NAME` |
| Embedding model | `publishers/google/models/text-embedding-005`, sent as `projects/{project}/locations/{RAG_LOCATION}/publishers/google/models/text-embedding-005` | `RagCorpus.vector_db_config.rag_embedding_model_config.vertex_prediction_endpoint.endpoint` |
| Vector database | RAG-managed, the service default; left unset | n/a |
| Chunking | fixed length, `chunk_size=1024`, `chunk_overlap=200` | `UploadRagFileConfig.rag_file_transformation_config.rag_file_chunking_config.fixed_length_chunking` |
| Upload path | `build/corpus/<doc_id>.md` | `corpus_sync` |
| File display name | `<doc_id>__<sha12>.md`, for example `gdpr__3f9a1c0b7d2e.md` | hash of the rendered text plus the chunk settings |
| Region | `RAG_LOCATION`, default `us-east4` | `.env` |
| SDK | `agentplatform.Client(project=..., location=RAG_LOCATION).rag` from `google-cloud-agentplatform` 2.10.0 | `corpus_sync.AgentPlatformRagClient` |

The calls, with type names checked against the 2.10.0 source:

```python
import agentplatform
from agentplatform import types

client = agentplatform.Client(project=project, location=rag_location)

corpus = client.rag.create_corpus(
    rag_corpus=types.RagCorpus(
        display_name="policypulse-5docs-corpus",
        description=(
            "PolicyPulse: GDPR, HIPAA Privacy Rule Summary, NCSP 2013, "
            "National Road Safety Policy 2010, Customer Registration API spec"
        ),
        vector_db_config=types.RagVectorDbConfig(
            rag_embedding_model_config=types.RagEmbeddingModelConfig(
                vertex_prediction_endpoint=types.RagEmbeddingModelConfigVertexPredictionEndpoint(
                    endpoint=(
                        f"projects/{project}/locations/{rag_location}"
                        "/publishers/google/models/text-embedding-005"
                    ),
                ),
            ),
        ),
    ),
)  # create_corpus waits for the long-running operation to finish

upload_config = types.UploadRagFileConfig(
    rag_file_transformation_config=types.RagFileTransformationConfig(
        rag_file_chunking_config=types.RagFileChunkingConfig(
            fixed_length_chunking=types.RagFileChunkingConfigFixedLengthChunking(
                chunk_size=1024,
                chunk_overlap=200,
            ),
        ),
    ),
)

rag_file = client.rag.upload_file(
    corpus_name=corpus.name,
    path="build/corpus/gdpr.md",
    display_name="gdpr__3f9a1c0b7d2e.md",
    upload_rag_file_config=upload_config,
)
```

Register `text/markdown` for `.md` with `mimetypes.add_type` before uploading. `upload_file` guesses the MIME type from the path and falls back to `application/octet-stream`, and older Python versions do not map `.md` (observed in the SDK source; Python 3.14 maps it).

### How titles and article numbers survive chunking

Each citation block renders like this:

```markdown
### GDPR > Chapter IV Controller and processor > Section 2 Security of personal data > Article 33 Notification of a personal data breach to the supervisory authority > Paragraph 1
Cite as: GDPR Art. 33(1)

In the case of a personal data breach, the controller shall without undue delay and, where feasible, not later than 72 hours after having become aware of it, notify the personal data breach to the supervisory authority competent in accordance with Article 55, unless ...

End of GDPR Art. 33(1)
```

- **One block per smallest citation unit:** a GDPR paragraph, point, definition or recital; an NCSP objective or strategy paragraph; a HIPAA section paragraph with its page; a Road Safety Policy section; a Registration API heading section.
- **Long blocks split.** A block over 350 words splits at sentence boundaries, and each part repeats the heading, `Cite as:` and `End of` lines. At the 1.33 tokens per word typical of English legal text (derived), 350 words is about 470 tokens, well under the 824-token stride between chunk starts (1024 minus 200). Every chunk therefore contains at least one complete marker line. A Hypothesis property test checks the word-level version: every 600-word window of rendered output contains a `Cite as:` or an `End of` line.
- **Leading partial blocks.** Text at the start of a chunk, before its first `Cite as:` line, belongs to the label on the next `End of` line. The prompt states this rule.
- **Display names serve operators.** In function-call mode the model never sees the file name, so the display name carries only the doc id and content hash for idempotency and for reading the corpus in the console.
- **Metadata tagging.** Per-file user metadata cannot be set through `upload_file` in this SDK version (observed). Document identity therefore travels three ways: in the in-text labels, in the display name, and in the corpus description.

| Document | Source file | Citation name | Label examples | Split rule |
| --- | --- | --- | --- | --- |
| GDPR, Regulation (EU) 2016/679 | `gdpr_regulation_2016_679.pdf` | `GDPR` | `GDPR Art. 33(1)`, `GDPR Art. 5(1)(c)`, `GDPR Art. 4(7)`, `GDPR Recital 85` | Before "HAVE ADOPTED THIS REGULATION", a line starting `(n)` is a recital only when n is the previous recital plus one; other `(n)` lines are footnotes and are dropped. In the body, `CHAPTER`, `Section` and `Article N` plus the next line give the breadcrumb. `N.` starts a paragraph and `(a)` starts a point. `(i)` is point i only when the previous point was `(h)`; otherwise it is a roman sub-point kept inside its point. In Article 4, sequential `(n)` lines are definitions. Official Journal running headers and footers are stripped. |
| Summary of the HIPAA Privacy Rule (HHS Office for Civil Rights) | `privacysummary.pdf` | `HIPAA Privacy Rule Summary` | `HIPAA Privacy Rule Summary, Minimum Necessary, p. 10`, `HIPAA Privacy Rule Summary, Criminal Penalties, p. 17` | Split on the ordered list of the summary's section and subsection headings held in the registry. The page number comes from the pypdf page index. A missing heading fails the contract gate. |
| National Cyber Security Policy 2013 (India) | `national_cyber_security_policy_2013.pdf` | `NCSP 2013` | `NCSP 2013, Objective 8`, `NCSP 2013, Strategy E`, `NCSP 2013, Preamble` | Roman-numeral sections (Preamble, Vision, Mission, Objectives, Strategies, Operationalisation); numbered objectives; lettered strategies with their titles; one block per paragraph or bullet inside a strategy. |
| National Road Safety Policy (India, 2010) | `national_road_safety_policy_2010.pdf` | `Road Safety Policy` | `Road Safety Policy, para 4`, `Road Safety Policy, Introduction` | Numbered sections; unnumbered opening text is `Introduction`. Provisional until the real file is in `docs/`, because the fixture is cut from it. |
| Customer Registration API spec | `customer_registration_api_spec.md` or `.pdf` | `Registration API` | `Registration API, Duplicate detection`, `Registration API, Fuzzy screening > Timeout` | Markdown ATX headings (`#` to `####`) outside fenced code; the heading path is the locator. A `.pdf` copy splits on numbered headings matching `^\d+(\.\d+)*\s`. Provisional until the file name and format are known. |

Text extraction joins wrapped lines inside a block and removes a line-end hyphen only when the next line starts in lowercase. Page numbers count PDF pages from 1.

**Contract gate before upload.** For each document the registry declares the labels that must exist and a block-count range. Examples: GDPR Articles 1 to 99 and Recitals 1 to 173; NCSP Objectives 1 to 14 and Strategies A to N; every HIPAA heading in the list. These counts are derived from the published texts and get confirmed on the first `--render-only` run against the real files. A failed gate stops the run before any GCP call.

### Idempotency design

**Corpus level**

1. List corpora, following `next_page_token`, and keep those whose display name is `policypulse-5docs-corpus`.
2. If none match, create the corpus. If one matches, reuse it after checking that its embedding endpoint ends in `publishers/google/models/text-embedding-005`; on a mismatch, stop and print "run with --recreate". If two or more match, stop and print their resource names. The script never picks one.
3. `--recreate` deletes every file in each matching corpus, then deletes the corpus, then creates a fresh one. Files go first because the SDK exposes no force option on corpus deletion (observed).

**File level**, keyed by doc id

| Remote state for the doc id | Action |
| --- | --- |
| No file | Upload |
| One ACTIVE file with the current hash | Skip |
| One file with a different hash | Upload the new file, wait for ACTIVE, then delete the old one |
| Several files, left by an interrupted run | Keep the ACTIVE file with the current hash (upload one if missing) and delete the rest |
| File in ERROR | Delete it and upload again; a second ERROR stops the run and prints the file's status |
| Display name with no known doc id | Report as stray and leave it; only `--recreate` removes it |

- **Hash:** sha256 over the rendered markdown bytes plus `chunk_size=1024 chunk_overlap=200 splitter_version=1`, first 12 hex characters.
- **Waiting:** after each upload, read `file_status.state`. If it is not ACTIVE, poll `get_file` every 5 seconds for up to 10 minutes, then fail naming the file. Sleep and clock are injected, so unit tests run instantly.
- **Read-back:** after the sync, `get_corpus` prints the embedding endpoint the service stored. This settles the PARTIAL claim about which corpus field the service honors.
- **`.env`:** upsert `RAG_CORPUS_RESOURCE_NAME=<corpus.name>` in the repo-root `.env`. The upsert creates the file if missing, replaces the line if present, leaves other lines alone, and writes through a temp file and rename.
- **Exit codes:** 0 on success; 1 on a runtime failure; 2 on a usage error (missing env var, or a missing or ambiguous source file).
- **Repeatability:** a second run with nothing changed prints five `skip` lines, uploads nothing, and leaves `.env` byte-identical.

## 3. ADK Agent & `VertexAiRagRetrieval` Configuration (`policypulse_rag/agent.py`)

```python
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

    On Gemini models the parent class attaches a server-side retrieval tool,
    which leaves no tool call in the event stream. Declaring a function lets the
    model choose its own queries, one per document for cross-document questions,
    and makes every search visible in adk web traces and adk eval trajectories.
    """

    async def process_llm_request(self, *, tool_context, llm_request) -> None:
        # Bypass the parent's Gemini branch; BaseTool declares the function.
        await super(VertexAiRagRetrieval, self).process_llm_request(
            tool_context=tool_context, llm_request=llm_request
        )


def build_retrieval_tool(rag_corpus: str) -> PolicyDocsRetrieval:
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
    return LlmAgent(
        name="policypulse_rag",
        model=model,
        description="Answers questions about five policy and specification documents with citations.",
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
```

- **`rag_resources` type.** The brief writes `RagResource(rag_corpus=...)`. In 2.14.1 the native type is `google.genai.types.VertexRagStoreRagResource`, and `vertexai.rag.RagResource` still works through structural typing (observed). The plan uses the native type because importing `vertexai.rag` now emits a deprecation warning.
- **`similarity_top_k=10`** returns up to 10 chunks per call, about 10,000 tokens. Q12 makes 2 to 4 calls, so the worst case is about 40,000 tokens of context, far inside the Flash window (derived).
- **`vector_distance_threshold=0.6`** keeps chunks whose cosine distance is at most 0.6 on the 0 to 2 scale (derived from the score definition). The live recall test confirms that every expected label passes this cut, and records the best distance seen for Q13.
- **`temperature=0.0`** keeps eval runs comparable.
- **Model switch:** set `POLICYPULSE_MODEL=gemini-2.5-pro` in `.env` to use Pro. No code changes.

**Environment variables (`.env.example`)**

| Variable | Example | Read by |
| --- | --- | --- |
| `GOOGLE_GENAI_USE_ENTERPRISE` | `1` | ADK and google-genai: route Gemini calls through Vertex AI |
| `GOOGLE_CLOUD_PROJECT` | `your-project-id` | ADK, ingest |
| `GOOGLE_CLOUD_LOCATION` | `us-east4` (or `global`) | Gemini endpoint region |
| `RAG_LOCATION` | `us-east4` | ingest; falls back to `GOOGLE_CLOUD_LOCATION` |
| `POLICYPULSE_MODEL` | `gemini-2.5-flash` | `agent.py` |
| `RAG_CORPUS_RESOURCE_NAME` | written by the ingest | `agent.py` |

### System prompt (`policypulse_rag/prompts.py`, `INSTRUCTION`)

The text contains no curly braces, because ADK reads `{identifier}` as a session-state placeholder (observed). A unit test enforces this.

```text
You are PolicyPulse, a question-answering assistant for five reference documents. You answer only from passages returned by the search_policy_documents tool.

DOCUMENTS AND CITATION NAMES
- Registration API: the Customer Registration API specification. It covers duplicate detection, fuzzy duplicate screening with Gemini, the screening timeout fallback, and the candidate cap.
- GDPR: Regulation (EU) 2016/679, the EU General Data Protection Regulation.
- HIPAA Privacy Rule Summary: the US HHS Office for Civil Rights summary of the HIPAA Privacy Rule. It covers protected health information (PHI) held by US covered entities and their business associates.
- NCSP 2013: India's National Cyber Security Policy 2013.
- Road Safety Policy: India's National Road Safety Policy, approved in 2010.

RULE 1. SEARCH BEFORE EVERY ANSWER
Call search_policy_documents at least once for every user message before you write anything, including questions that look out of scope. Never answer from memory or general knowledge, even when you are confident you know the answer.

RULE 2. CITE EVERY FACTUAL CLAIM
Each passage is made of blocks. A block starts with a breadcrumb heading and a line "Cite as: LABEL", and ends with a line "End of LABEL". Text that appears before the first "Cite as:" line of a passage belongs to the label on the next "End of" line.
Put the label in square brackets right after each sentence that uses the block, copied exactly. Examples: [GDPR Art. 33(1)], [GDPR Recital 85], [NCSP 2013, Objective 8], [HIPAA Privacy Rule Summary, Minimum Necessary, p. 10], [Road Safety Policy, para 4], [Registration API, Duplicate detection].
Never write an article, paragraph, objective, strategy, section, or page number that does not appear in a label. When two blocks support one sentence, cite both, for example [GDPR Art. 83(5)] [GDPR Art. 83(6)]. When an Article and a Recital say the same thing, cite the Article.

RULE 3. QUESTIONS THAT SPAN DOCUMENTS
When a question involves more than one document, for example how the Registration API handles customer data and what privacy law requires, call search_policy_documents once for each document involved, with a query that names the document and the topic. Answer with one short paragraph or bullet per document, each with its own citations, and finish with one sentence that connects them. Mention a document only when a retrieved block supports the point.

RULE 4. OUT OF SCOPE
If the retrieved passages do not answer the question, or the tool reports no matching result, reply with exactly this sentence and nothing else:
The provided reference documents do not cover this topic.
Do not add a guess, a number, general knowledge, or advice on where to look. If the passages answer part of the question, answer that part with citations and use the same sentence for the rest.

RULE 5. HIPAA AND GDPR ARE DIFFERENT LAWS
The HIPAA Privacy Rule Summary covers US protected health information held by covered entities and business associates. GDPR covers personal data under EU law. Never attribute a HIPAA rule to GDPR or a GDPR rule to HIPAA. "Minimum necessary" is the HIPAA standard. "Data minimisation" is the GDPR principle in Art. 5(1)(c). When a question names one law, answer from that law only. When a question is about health data without naming a law, say which law each point comes from.

ANSWER STYLE
Lead with the direct answer. Use plain sentences or short bullets. Keep amounts, dates, durations, and names exactly as the passage writes them.
```

`prompts.py` also exports `REFUSAL_SENTENCE = "The provided reference documents do not cover this topic."` and `CITATION_NAMES` (the five names above). The example labels in Rule 2 for the Road Safety Policy and the Registration API follow the provisional label formats; they change together with those splitters, and a unit test keeps every example label matching its document's label pattern.

## 4. Acceptance Test Matrix & Edge-Case Handling (Q1–Q13)

### The 13 acceptance Q&As (user-provided, verbatim)

1. **Q1.** What status does the registration API return for an exact duplicate, and how is it detected?
   **A:** 409 duplicate-customer. It's detected deterministically on normalized email first, then E.164 phone.
2. **Q2.** What happens if Gemini times out during fuzzy duplicate screening?
   **A:** After the 8 s timeout, the API falls back to deterministic only and still registers the customer (201 "created, unscreened", with a warning banner). The model can only flag a possible duplicate for review and never causes a hard rejection.
3. **Q3.** How many candidates go to Gemini per call, and why?
   **A:** At most 5. The cap limits tokens and the amount of PII sent to the model.
4. **Q4.** How quickly must a personal data breach be reported under GDPR?
   **A:** Without undue delay and, where feasible, within 72 hours of becoming aware of it, to the supervisory authority. This doesn't apply if the breach is unlikely to put people's rights and freedoms at risk. A late notification must give reasons for the delay. [GDPR Art. 33(1)]
5. **Q5.** What is the maximum GDPR fine?
   **A:** Up to €20 million or 4% of total worldwide annual turnover for the previous financial year, whichever is higher. [GDPR Art. 83(5)–(6)]
6. **Q6.** What is the "minimum necessary" principle under HIPAA?
   **A:** Covered entities must make reasonable efforts to use, disclose and request only the minimum PHI needed for the purpose. It doesn't apply in some cases, such as disclosures to a provider for treatment or to the individual themselves. [HIPAA Privacy Rule Summary]
7. **Q7.** What criminal penalties does HIPAA set for wrongful disclosure?
   **A:** Knowingly obtaining or disclosing: up to $50,000 and 1 year in prison. Under false pretenses: $100,000 and 5 years. With intent to sell or use for commercial advantage, personal gain or malicious harm: $250,000 and 10 years. [HIPAA Privacy Rule Summary]
8. **Q8.** What workforce target does India's National Cyber Security Policy 2013 set?
   **A:** 500,000 skilled cyber security professionals within 5 years, through capacity building, skill development and training. [NCSP 2013, Objective 8]
9. **Q9.** Which 24x7 bodies does the cyber security policy set up?
   **A:** CERT-In as the national nodal agency for cyber emergency response, sectoral CERTs, and NCIIPC for critical information infrastructure protection. [NCSP 2013, Strategies E & G]
10. **Q10.** When was the National Road Safety Policy approved, and on whose recommendation?
    **A:** The Union Cabinet approved it on 15 March 2010, based on the Sundar Committee (chaired by S. Sundar, former Secretary MoST), which reported in February 2007. [Road Safety Policy]
11. **Q11.** How will road safety activities be funded and overseen?
    **A:** Through a National Road Safety Fund, financed by a share of the cess on petrol and diesel, with a National Road Safety Board overseeing implementation. [Road Safety Policy]
12. **Q12 (cross-document).** Our registration API sends customer data to Gemini. What in these docs supports limiting what we send?
    **A:** The answer should combine and cite: the API caps candidates at 5 and sends only a minimized screening profile [Registration API]; GDPR data minimisation [Art. 5(1)(c)]; HIPAA "minimum necessary" if health data is involved; NCSP Objective 10 on protecting data in process, storage and transit.
13. **Q13 (out of scope).** What is the speed limit on Indian national highways?
    **A:** The agent should say the documents don't cover this. It must not guess.

### Verification matrix

| Test ID and category | Target source | Required citation and key facts | Retrieval risk | Mitigation |
| --- | --- | --- | --- | --- |
| Q1, API behavior | Registration API | `[Registration API, ...]`; 409; `duplicate-customer`; deterministic match on normalized email first, then E.164 phone | A short spec, where "exact duplicate" text may share a chunk with fuzzy screening text | Heading-level blocks; one rubric per fact |
| Q2, API failure mode | Registration API | 8 s timeout; deterministic-only fallback; customer still registered with 201 "created, unscreened" and a warning banner; the model only flags for review and never hard-rejects | Facts spread across timeout and outcome subsections | top_k 10 brings sibling blocks; four rubrics |
| Q3, API limit | Registration API | At most 5 candidates; the cap limits tokens and the PII sent | The number is easy to state without the reason | A rubric requires the reason |
| Q4, GDPR article | GDPR | `[GDPR Art. 33(1)]`; without undue delay and, where feasible, within 72 hours of becoming aware; to the supervisory authority; exception when the breach is unlikely to result in a risk; a late notification gives reasons | Article 34 and Recitals 85 to 88 also mention breaches and 72 hours | Paragraph-level labels; Rule 2 prefers the Article; a rubric requires Art. 33 |
| Q5, GDPR article | GDPR | `[GDPR Art. 83(5)]` and/or `[GDPR Art. 83(6)]`; €20 million or 4% of total worldwide annual turnover of the preceding financial year, whichever is higher | Art. 83(4) states €10 million or 2%; Article 83 spans several chunks | One block per paragraph; a rubric fails an answer that gives €10 million or 2% as the maximum |
| Q6, HIPAA principle | HIPAA summary | `[HIPAA Privacy Rule Summary, ...]`; reasonable efforts to use, disclose and request only the minimum necessary PHI; at least one exception (disclosure to a provider for treatment, or to the individual) | Confusion with GDPR data minimisation | Rule 5; a rubric fails attribution to GDPR |
| Q7, HIPAA penalties | HIPAA summary | $50,000 and 1 year (knowingly); $100,000 and 5 years (false pretenses); $250,000 and 10 years (intent to sell, commercial advantage, personal gain, malicious harm) | Civil money penalties sit in the adjacent subsection | Criminal Penalties is its own block; one rubric per tier |
| Q8, NCSP objective | NCSP 2013 | `[NCSP 2013, Objective 8]`; 500,000 professionals; 5 years; capacity building, skill development and training | The objective list may extract as one run-on paragraph | The splitter separates numbered objectives; the gate requires Objective 8 |
| Q9, NCSP strategies | NCSP 2013 | `[NCSP 2013, Strategy E]` and `[NCSP 2013, Strategy G]`; CERT-In as the 24x7 national nodal agency; sectoral CERTs; NCIIPC operating 24x7 for critical information infrastructure | The answer needs two strategies; "24x7" may appear as "24 x 7" | top_k 10; one rubric per body |
| Q10, Road Safety history | Road Safety Policy | Union Cabinet approval on 15 March 2010; Sundar Committee chaired by S. Sundar, former Secretary MoST; the committee reported in February 2007 | The facts may sit in an unnumbered preface. Whether the PDF states them at all is UNVERIFIED | `Introduction` block; the render step confirms the facts are in the file (open evidence gap) |
| Q11, Road Safety funding | Road Safety Policy | National Road Safety Fund; financed by a share of the cess on petrol and diesel; National Road Safety Board oversees implementation | Fund and Board may sit in different sections | top_k 10; one rubric per fact |
| Q12, cross-document | Registration API, GDPR, HIPAA summary, NCSP 2013 | Cap of 5 and a minimized screening profile `[Registration API]`; data minimisation `[GDPR Art. 5(1)(c)]`; HIPAA minimum necessary when health data is involved `[HIPAA Privacy Rule Summary]`; protecting data in process, storage and transit `[NCSP 2013, Objective 10]` | One broad query returns one or two documents; HIPAA must be conditional on health data | Rule 3 (one search per document); the trajectory expects at least two calls; one rubric per source |
| Q13, out of scope | none | Exactly the refusal sentence; no speed value; no general knowledge | Road Safety Policy chunks may pass the 0.6 threshold and invite a guess | Rules 1 and 4; a rubric fails any number; `hallucinations_v1` |

### Edge cases

- **No result above the threshold.** `run_async` returns the string "No matching result found with the config: ..." (observed). Rule 4 turns that into the refusal sentence. The string includes the corpus resource name, so raw tool responses stay out of the committed `eval/runs/` summaries.
- **Partial coverage.** A question that is half in scope gets the cited half plus the refusal sentence (Rule 4).
- **A question naming the wrong law**, for example "minimum necessary under GDPR". Rule 5 answers from the named law's passages, or refuses.
- **Follow-up turns** in the same `adk web` session work, because each turn searches again. They are not part of the eval set.

## 5. ADK Evaluation Harness (`adk eval`)

### `eval/policypulse_evalset.json` schema (validated against `google-adk` 2.14.1)

The first case in full:

```json
{
  "eval_set_id": "policypulse_evalset",
  "name": "PolicyPulse acceptance Q1-Q13",
  "description": "The 13 acceptance questions. Each case expects at least one search_policy_documents call and is scored by per-case rubrics.",
  "eval_cases": [
    {
      "eval_id": "q01_exact_duplicate_status",
      "session_input": { "app_name": "policypulse_rag", "user_id": "eval_user", "state": {} },
      "conversation": [
        {
          "invocation_id": "q01_exact_duplicate_status_turn1",
          "user_content": {
            "role": "user",
            "parts": [{ "text": "What status does the registration API return for an exact duplicate, and how is it detected?" }]
          },
          "final_response": {
            "role": "model",
            "parts": [{ "text": "409 duplicate-customer. It's detected deterministically on normalized email first, then E.164 phone." }]
          },
          "intermediate_data": {
            "tool_uses": [
              { "name": "search_policy_documents", "args": { "query": "registration API exact duplicate status code and detection" } }
            ],
            "tool_responses": [],
            "intermediate_responses": []
          }
        }
      ],
      "rubrics": [
        { "rubric_id": "q01_cites_api", "type": "FINAL_RESPONSE_QUALITY", "rubric_content": { "text_property": "The response cites the Registration API document in square brackets." } },
        { "rubric_id": "q01_status_409", "type": "FINAL_RESPONSE_QUALITY", "rubric_content": { "text_property": "The response states that an exact duplicate returns HTTP 409 with duplicate-customer." } },
        { "rubric_id": "q01_detection_order", "type": "FINAL_RESPONSE_QUALITY", "rubric_content": { "text_property": "The response says detection is deterministic, on normalized email first and then on E.164 phone." } }
      ]
    }
  ]
}
```

**Encoding rules for all 13 cases**

- `user_content` is the question text verbatim from the list above, without the "(cross-document)" or "(out of scope)" tags.
- `final_response` is the answer text verbatim for Q1 to Q11. The user's Q12 and Q13 entries describe what the answer must contain, so those cases carry an answer-form reference (below), and the verbatim expectation goes into their rubrics.
- `tool_uses` names `search_policy_documents`. Q12 lists two calls; every other case lists one. The `query` values are indicative only, because the criterion ignores arguments.
- Every rubric carries `"type": "FINAL_RESPONSE_QUALITY"`. Without that type the evaluator filters the rubric out (observed).
- **Q12 reference (derived from the user's expectation):** "Several documents support limiting what the API sends. The Registration API caps fuzzy-screening candidates at 5 per Gemini call and sends only a minimized screening profile [Registration API]. GDPR requires personal data to be adequate, relevant and limited to what is necessary (data minimisation) [GDPR Art. 5(1)(c)]. If health data is involved, HIPAA's minimum necessary standard limits uses and disclosures of PHI to the minimum needed [HIPAA Privacy Rule Summary]. NCSP 2013 Objective 10 calls for protecting information while in process, handling, storage and transit [NCSP 2013, Objective 10]."
- **Q13 reference:** "The provided reference documents do not cover this topic."

| eval_id | Search calls | Case rubrics (`text_property`, abbreviated) |
| --- | --- | --- |
| `q01_exact_duplicate_status` | 1 | cites Registration API; 409 with duplicate-customer; deterministic, normalized email first then E.164 phone |
| `q02_gemini_timeout_fallback` | 1 | cites Registration API; 8 s timeout then deterministic-only screening; customer still registered, 201 "created, unscreened" with a warning banner; Gemini can only flag for review and never causes a hard rejection |
| `q03_candidate_cap` | 1 | cites Registration API; at most 5 candidates per call; the reason is limiting tokens and the PII sent to the model |
| `q04_gdpr_breach_notification` | 1 | cites GDPR Art. 33 (paragraph 1); without undue delay and, where feasible, within 72 hours of becoming aware; to the supervisory authority; not required when the breach is unlikely to result in a risk to rights and freedoms; a late notification gives reasons for the delay |
| `q05_gdpr_max_fine` | 1 | cites GDPR Art. 83(5) or 83(6); €20 million or 4% of total worldwide annual turnover of the preceding financial year; whichever is higher; does not present €10 million or 2% as the maximum |
| `q06_hipaa_minimum_necessary` | 1 | cites HIPAA Privacy Rule Summary; reasonable efforts to use, disclose and request only the minimum necessary PHI; names at least one exception (treatment disclosure to a provider, or disclosure to the individual); does not attribute the standard to GDPR |
| `q07_hipaa_criminal_penalties` | 1 | cites HIPAA Privacy Rule Summary; $50,000 and 1 year for knowing disclosure; $100,000 and 5 years under false pretenses; $250,000 and 10 years with intent to sell or use for commercial advantage, personal gain or malicious harm; does not present civil penalties as criminal |
| `q08_ncsp_workforce_target` | 1 | cites NCSP 2013 Objective 8; 500,000 skilled professionals; within 5 years; through capacity building, skill development and training |
| `q09_ncsp_24x7_bodies` | 1 | cites NCSP 2013 Strategy E and Strategy G; CERT-In as the 24x7 national nodal agency for cyber emergency response; sectoral CERTs; NCIIPC 24x7 for critical information infrastructure protection |
| `q10_road_safety_approval` | 1 | cites Road Safety Policy; Union Cabinet approval on 15 March 2010; on the recommendation of the Sundar Committee chaired by S. Sundar, former Secretary MoST; the committee reported in February 2007 |
| `q11_road_safety_funding` | 1 | cites Road Safety Policy; National Road Safety Fund; financed by a share of the cess on petrol and diesel; National Road Safety Board oversees implementation |
| `q12_cross_doc_data_limits` | 2 | cites Registration API for the cap of 5 and the minimized screening profile; cites GDPR Art. 5(1)(c) data minimisation; mentions HIPAA minimum necessary, conditional on health data, citing the HIPAA summary; cites NCSP 2013 Objective 10 on protecting data in process, storage and transit; each point is attributed to its own document; verbatim expectation: "The answer should combine and cite: the API caps candidates at 5 and sends only a minimized screening profile [Registration API]; GDPR data minimisation [Art. 5(1)(c)]; HIPAA "minimum necessary" if health data is involved; NCSP Objective 10 on protecting data in process, storage and transit." |
| `q13_out_of_scope_speed_limit` | 1 | says the provided reference documents do not cover the topic; states no speed value or any other number; offers no answer from general knowledge; verbatim expectation: "The agent should say the documents don't cover this. It must not guess." |

### `eval/test_config.json`

```json
{
  "criteria": {
    "tool_trajectory_avg_score": {
      "threshold": 1.0,
      "match_type": "IN_ORDER",
      "ignore_args": true
    },
    "rubric_based_final_response_quality_v1": {
      "threshold": 0.8,
      "judge_model_options": { "judge_model": "gemini-2.5-flash", "num_samples": 3 },
      "rubrics": [
        {
          "rubric_id": "grounded_only",
          "type": "FINAL_RESPONSE_QUALITY",
          "rubric_content": {
            "text_property": "Every factual statement in the response is supported by text returned by the search_policy_documents tool, and the response adds no facts from general knowledge."
          }
        }
      ]
    },
    "hallucinations_v1": {
      "threshold": 0.8,
      "judge_model_options": { "judge_model": "gemini-2.5-flash", "num_samples": 1 }
    },
    "response_match_score": 0.3
  },
  "multi_run_config": {
    "cross_run_criteria": [{ "method": "pass_rate", "threshold": 0.66 }]
  }
}
```

- **Trajectory:** `IN_ORDER` with `ignore_args` passes when the expected `search_policy_documents` calls appear in order. Extra calls are allowed, and the model-generated query text is ignored.
- **Rubrics** carry the semantic check: correct source, key facts, no invented facts. They tolerate paraphrase, which is the gap ROUGE leaves.
- **`response_match_score` stays as a lexical floor at 0.3**, far below the 0.8 default, because a correct cited paraphrase scores well under 0.8. After the first run where every rubric passes, set it to the lowest observed per-case score minus 0.05, never below 0.2, and record the scores in `eval/runs/`.
- **`pass_rate` 0.66** applies when `--num_runs 3` is given: each case must pass in at least 2 of 3 runs. With a single run, a case must pass outright.
- **Judge model:** if `gemini-2.5-flash` is not served, change `judge_model` in both criteria to the model that passed the runbook preflight.

### Commands

```bash
# Whole set; adk eval reads eval/test_config.json because it sits next to the eval set.
adk eval policypulse_rag eval/policypulse_evalset.json --print_detailed_results

# Same, with the config named explicitly.
adk eval policypulse_rag eval/policypulse_evalset.json --config_file_path eval/test_config.json

# Selected cases.
adk eval policypulse_rag eval/policypulse_evalset.json:q12_cross_doc_data_limits,q13_out_of_scope_speed_limit

# Final gate: three runs per case; each case must pass 2 of 3.
adk eval policypulse_rag eval/policypulse_evalset.json --num_runs 3 --print_detailed_results
```

### Reading the scores

| Metric | Score meaning | Threshold | What a failure points to |
| --- | --- | --- | --- |
| `tool_trajectory_avg_score` | 1.0 when every expected search call appears in order | 1.0 | 0.0 means the agent answered without searching (Rule 1), or searched only once on Q12 (Rule 3) |
| `rubric_based_final_response_quality_v1` | Share of rubrics the judge marks satisfied, by majority over 3 samples | 0.8 | The detailed results name the failed rubric: a missing citation, a missing fact, or a wrong number |
| `hallucinations_v1` | Share of response sentences supported by the tool output | 0.8 | A sentence drawn from general knowledge, or a citation label the chunks do not contain |
| `response_match_score` | ROUGE-1 F-measure against the reference text | 0.3 (calibrated) | Only a large wording drift; never the sole reason to change a correct answer |
| `tool_call_count_v1`, `inference_call_count_v1`, `token_usage_v1`, `invocation_duration_v1` | Informational, reported on every run | none | Cost and latency trends between runs |

Raw results land in `policypulse_rag/.adk/eval_history/` (gitignored). After each run, commit a summary to `eval/runs/<YYYY-MM-DD>-<label>.md` with the git SHA, model, ADK version, and a pass/fail table per case and metric. Leave raw tool responses out of the summary.

## 6. Execution Runbook (Step-by-Step)

```bash
# 0. Values used below; set them once per shell.
export PROJECT_ID="your-project-id"
export RAG_LOCATION="us-east4"            # RAG Engine region; fallback europe-west4
export GOOGLE_CLOUD_LOCATION="us-east4"   # Gemini region, or "global"
export POLICYPULSE_MODEL="gemini-2.5-flash"

# 1. Project, API, IAM. A project owner runs the binding once.
gcloud config set project "$PROJECT_ID"
gcloud services enable aiplatform.googleapis.com --project "$PROJECT_ID"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:$(gcloud config get-value account)" \
  --role="roles/aiplatform.user" \
  --condition=None

# 2. Application Default Credentials for the SDKs. No key files.
gcloud auth application-default login
gcloud auth application-default set-quota-project "$PROJECT_ID"

# 3. Preflight: RAG Engine accepts this project in this region.
#    Expect {} or a "ragCorpora" list. An allowlist or FAILED_PRECONDITION error means: pick another region.
TOKEN="$(gcloud auth print-access-token)"
curl -sS -H "Authorization: Bearer $TOKEN" \
  "https://${RAG_LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${RAG_LOCATION}/ragCorpora"

# 4. Preflight: the model answers in GOOGLE_CLOUD_LOCATION. Expect a "candidates" array.
#    A 404 means the model is not served there: try another region, or set POLICYPULSE_MODEL to another model.
#    For GOOGLE_CLOUD_LOCATION=global the host is aiplatform.googleapis.com without a region prefix.
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://${GOOGLE_CLOUD_LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${GOOGLE_CLOUD_LOCATION}/publishers/google/models/${POLICYPULSE_MODEL}:generateContent" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Reply with OK."}]}]}'

# 5. Python environment.
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

# 6. Configuration. Fill in GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, RAG_LOCATION.
cp .env.example .env

# 7. Unit tests. No GCP access needed.
pytest -m "not live"

# 8. Source documents: five files in docs/, hashes matching docs/SOURCES.md.
ls docs/
sha256sum docs/*.pdf docs/customer_registration_api_spec.*

# 9. Render and inspect. No GCP calls.
python scripts/ingest_corpus.py --render-only
less build/corpus/gdpr.md

# 10. Ingest, then run again to prove repeatability. The second run prints five "skip" lines.
python scripts/ingest_corpus.py
python scripts/ingest_corpus.py
grep RAG_CORPUS_RESOURCE_NAME .env

# 11. Retrieval recall check against the live corpus.
pytest -m live tests/live -s

# 12. Demo. Run from the repo root, open http://localhost:8000, choose policypulse_rag,
#     and ask Q1 to Q13. Each answer shows search_policy_documents calls in the event trace.
adk web

# 13. Evaluation, then the final gate.
adk eval policypulse_rag eval/policypulse_evalset.json --print_detailed_results
adk eval policypulse_rag eval/policypulse_evalset.json --num_runs 3 --print_detailed_results

# 14. Optional rebuild from scratch.
python scripts/ingest_corpus.py --recreate
```

**Teardown after the demo:** delete the corpus in the Google Cloud console under Vertex AI, RAG Engine. If the project exists only for this demo, review the RAG Engine tier setting on the same page. Setting it to the unprovisioned tier deletes every corpus in the project and may stop managed-database charges (pricing UNVERIFIED).

## 7. Definition of Done (DoD) Checklist

- [ ] **Ingestion repeatability:** the first run creates `policypulse-5docs-corpus` with five ACTIVE files and writes `RAG_CORPUS_RESOURCE_NAME` to `.env`. A second run uploads nothing and leaves `.env` byte-identical. `--recreate` ends with one corpus holding five ACTIVE files.
- [ ] **Contract gate:** `--render-only` passes the gate for all five documents, and every rendered block carries `Cite as:` and `End of` lines.
- [ ] **Retrieval recall:** `pytest -m live` shows each expected label for Q1 to Q12 in the top 10 under the 0.6 threshold (Q12 checked per sub-query), with distances recorded.
- [ ] **13/13 accuracy with citations:** `adk eval ... --num_runs 3` passes all 13 cases, and every Q1 to Q12 answer carries at least one label from its target document.
- [ ] **Out-of-scope refusal:** Q13 returns exactly "The provided reference documents do not cover this topic." with no number, in every run.
- [ ] **`adk web` demo ready:** from a fresh clone, following the runbook, a reviewer asks Q1 to Q13 and sees the tool calls in the trace and the citations in each answer.
- [ ] **Architecture diagram delivered:** editable draw.io and Mermaid files from `/axis-diagram` in `.axis/diagrams/`, with the Mermaid version embedded in `README.md`.
- [ ] **TDD evidence, unit loop:** in git history each unit-tested module has a `test(...)` commit before its implementation commit; CI is green on `main` without GCP credentials.
- [ ] **TDD evidence, eval loop:** the eval set and `test_config.json` are committed before the first `agent.py`. `eval/runs/` holds the red baseline (ungrounded agent) and the final green run, with intermediate runs between them.
- [ ] **Hygiene:** no secret, key file or `.env` in git; `ruff check .` is clean; the README answers what it is, how to run it, how to test it, and where the design lives.

## Steps

**Committing for visible TDD.** Work each slice on a short branch. Commit the failing test first, for example `test(ingest): cover GDPR article and recital labels`. CI goes red on that commit. Then commit the implementation, for example `feat(ingest): split GDPR into article and recital blocks`, and CI goes green. Merge with a merge commit, never a squash, so each red-to-green pair survives on `main`. Subjects follow `type(scope): summary` from AGENTS.md, with scopes `agent`, `ingest`, `eval`, `ci`, `docs`.

**Foundation**

1. `[.gitignore:15]` Append below the AXIS block: `.env`, `.venv/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.ruff_cache/`, `.hypothesis/`, `build/`, `*.egg-info/`, `policypulse_rag/.adk/`, and `docs/customer_registration_api_spec.*` (pending the open question on the spec). Append only lines that are not already present. Test impact: none.
2. `[new file: pyproject.toml]` Project `policypulse-rag`, `requires-python = ">=3.11,<3.14"`. Dependencies: `google-adk[gcp]==2.14.1`, `google-cloud-agentplatform==2.10.0`, `pypdf>=5`, `python-dotenv>=1,<2`. Dev extra: `google-adk[eval]==2.14.1`, `google-cloud-aiplatform[evaluation]==2.10.0`, `pytest>=9,<10`, `pytest-asyncio>=0.25`, `pytest-randomly`, `hypothesis>=6`, `ruff`. Set `[tool.setuptools] packages = ["policypulse_rag"]`. Pytest: `pythonpath = [".", "scripts"]`, `testpaths = ["tests"]`, `addopts = "--import-mode=importlib"`, `asyncio_mode = "auto"`, `markers = ["live: needs ADC and a populated corpus; never runs in CI"]`. Ruff: `target-version = "py311"`, `line-length = 100`, lint `E,F,I,B,UP`. The ADK, agentplatform and aiplatform pins are exact because this plan's API claims were checked against those versions; both distributions ship identical `agentplatform/` files at 2.10.0 (observed). Test impact: enables the suite.
3. `[new file: .env.example]` The six variables in the environment table, with one comment line each and placeholder values. Test impact: none.
4. `[new file: .github/workflows/ci.yml]` On push and pull request: `permissions: contents: read`; checkout; setup-python 3.12 with pip cache; `pip install -e ".[dev]"`; `ruff check .`; `pytest -m "not live"`, which runs in random order through pytest-randomly and prints the seed. No secrets and no cloud authentication. Test impact: CI runs the unit suite.
5. `[AGENTS.md:101]` Append a `## Commands` section: setup, `pytest -m "not live"`, `pytest -m live`, `python scripts/ingest_corpus.py [--render-only|--recreate]`, `adk web`, `adk eval ...`. Record the suite budget: the unit suite stays under 60 s of wall-clock in CI, a test that needs a retry is a defect, and live tests never run in CI. Skip the append if the heading already exists. Test impact: none.
6. `[new file: docs/SOURCES.md]` One row per source file: title, issuing body, official URL (open question; fill in when known), retrieval date, sha256. Place the five files in `docs/`. The four public PDFs are committed; the API spec stays local unless its owning team agrees to a committed copy. Test impact: fixtures in later steps are cut from these files.

**Eval set before the agent**

7. `[new file: tests/unit/test_evalset_contract.py]` Red: the eval set file does not exist yet. The test cases are listed in the Test plan below.
8. `[new file: eval/policypulse_evalset.json]` and `[new file: eval/test_config.json]` Encode all 13 cases and the criteria exactly as the evaluation harness section specifies. Green: the contract test passes.
9. `[new file: policypulse_rag/__init__.py]` (`from . import agent`) and `[new file: policypulse_rag/agent.py]` Baseline agent: `LlmAgent(name="policypulse_rag", model=os.environ.get("POLICYPULSE_MODEL", "gemini-2.5-flash"), instruction="Answer the user's question.")` with no tools. With GCP access, run `adk eval policypulse_rag eval/policypulse_evalset.json --print_detailed_results` and commit the summary as `eval/runs/<date>-baseline.md`. Expected result: trajectory 0.0 on all 13 cases, citation rubrics failing, and Q13 likely answered with a guess. This run is the eval loop's red. If GCP access is not ready yet, commit the agent and record the baseline as pending; the git order still shows the eval set first.

**Preprocessing**

10. `[new file: tests/unit/test_blocks.py]` Red. Then `[new file: scripts/policypulse_ingest/__init__.py]` and `[new file: scripts/policypulse_ingest/blocks.py]`: a frozen `Block(doc_id, label, breadcrumb: tuple[str, ...], text, page: int | None)`, `render_blocks(blocks) -> str`, and `split_long_block(block, max_words=350) -> list[Block]`, which splits at sentence boundaries. Green.
11. `[new file: tests/fixtures/gdpr_excerpt.txt]` and `[new file: tests/unit/test_split_gdpr.py]` Red. The fixture is cut from the real PDF's extracted text: Recitals 85 and 86 with one Official Journal footnote; one running header; the Chapter IV and Section 2 headings; Article 4 definitions (1) and (2); Article 5(1) points (a) to (c); Article 33(1) and (2); Article 83(4) to (6). Then `[new file: scripts/policypulse_ingest/splitters/__init__.py]` and `[new file: scripts/policypulse_ingest/splitters/gdpr.py]`: `split_gdpr(pages: list[str]) -> list[Block]` following the GDPR split rule. Green.
12. `[new file: tests/fixtures/ncsp_excerpt.txt]` and `[new file: tests/unit/test_split_ncsp.py]` Red. The fixture covers Objectives 7 to 10, the opening and one bullet of Strategy E, and the opening of Strategy G. Then `[new file: scripts/policypulse_ingest/splitters/ncsp.py]`. Green.
13. `[new file: tests/fixtures/hipaa_pages.json]` and `[new file: tests/unit/test_split_hipaa.py]` Red. The fixture is page-indexed text for the Minimum Necessary section and for Enforcement and Penalties for Noncompliance (civil and criminal), with page breaks. Then `[new file: scripts/policypulse_ingest/splitters/hipaa.py]`, which takes the ordered heading list as a parameter. Green.
14. `[new file: tests/fixtures/road_safety_excerpt.txt]` and `[new file: tests/unit/test_split_road_safety.py]` Red. The fixture covers the opening text (approval date and committee, if present) and the Fund and Board sections. Then `[new file: scripts/policypulse_ingest/splitters/road_safety.py]`. Green. If the real structure differs from numbered sections, change the rule and state the actual rule in the module docstring.
15. `[new file: tests/fixtures/registration_api_spec.md]` (synthetic, with no real spec content) and `[new file: tests/unit/test_split_registration_api.py]` Red. Then `[new file: scripts/policypulse_ingest/splitters/registration_api.py]`, which handles both markdown and numbered-heading PDF text. Green.
16. `[new file: tests/unit/test_extract.py]` Red. Then `[new file: scripts/policypulse_ingest/extract.py]`: `read_pdf_pages(path) -> list[str]`, a thin pypdf boundary; `strip_lines(text, patterns)`; `join_wrapped_lines(text)`, which removes a line-end hyphen only before a lowercase letter. Green. The `--render-only` run on the real files exercises `read_pdf_pages`; unit tests leave it out.
17. `[new file: tests/unit/test_documents.py]` Red. Then `[new file: scripts/policypulse_ingest/documents.py]`: a `SourceDocument` registry for the five documents (doc id, accepted file names, citation name, label regex, splitter, expected labels, block-count range); `resolve_sources(docs_dir)`, which raises a usage error naming any missing or ambiguous file; and `check_contract(doc, blocks)`. Green.

**Ingestion**

18. `[new file: tests/unit/conftest.py]` Add `FakeRagClient`, an in-memory implementation of the `RagClient` protocol with injectable file states, plus a fake clock. It fakes the network boundary only. Then `[new file: tests/unit/test_corpus_sync.py]` Red, and `[new file: scripts/policypulse_ingest/corpus_sync.py]`: the `RagClient` protocol; `AgentPlatformRagClient`, a thin adapter over `agentplatform.Client(...).rag` that handles pagination; `build_corpus_spec(project, location)`; `build_upload_config()`; `content_hash(markdown)`; `plan_file_actions(remote_files, local_docs)`, a pure function; and `sync_corpus(client, docs, recreate, sleep, clock)`. Green. Safe to run twice by design; `--recreate` is the one destructive path, and re-running it ends in the same state.
19. `[new file: tests/unit/test_dotenv_file.py]` Red. Then `[new file: scripts/policypulse_ingest/dotenv_file.py]`: `upsert_env_value(path, key, value)` with a temp-file write and rename. Green.
20. `[new file: tests/unit/test_ingest_cli.py]` Red. Then `[new file: scripts/policypulse_ingest/cli.py]` (argparse with `--recreate`, `--render-only`, `--docs-dir`, `--env-file`, `--build-dir`; reads `GOOGLE_CLOUD_PROJECT` and `RAG_LOCATION` with `python-dotenv`; prints the summary table; returns the exit code) and `[new file: scripts/ingest_corpus.py]` (`raise SystemExit(main())`). Green.
21. Live, manual: run `--render-only` on the real files and read the rendered output. Where the real text breaks a split rule, first add the failing case to that splitter's fixture and test, then fix the rule. Confirm that the Q10 facts actually appear in the Road Safety Policy text. Then run the ingest twice and paste both summaries into the pull request.
22. `[new file: tests/live/conftest.py]` (skip unless `RAG_CORPUS_RESOURCE_NAME` is set and ADC is available) and `[new file: tests/live/test_retrieval_live.py]`: for Q1 to Q11, and for each of Q12's four sub-queries, call `retrieve_contexts` with the agent's store settings and assert that the expected label appears in the top 10. Print each expected chunk's distance and the best Q13 distance. Change the 0.6 threshold only with these recorded numbers.

**Agent**

23. `[new file: tests/unit/test_agent_wiring.py]` Red against the baseline agent. Then `[policypulse_rag/agent.py:1-end]` Replace the baseline with the full module from the agent configuration section. Green.
24. `[new file: tests/unit/test_prompts.py]` Red. Then `[new file: policypulse_rag/prompts.py]` with `INSTRUCTION`, `REFUSAL_SENTENCE` and `CITATION_NAMES` exactly as the system prompt section specifies. `agent.py` already imports `INSTRUCTION`. Green.
25. Live, manual: run `adk eval` and commit the summary under `eval/runs/`. For each failure, decide whether the cause is retrieval (fix a splitter or the threshold, test first) or generation (fix the prompt and extend `test_prompts.py` first). Repeat until 13/13, then run the `--num_runs 3` gate and calibrate `response_match_score` as the harness section describes.
26. Live, manual: run the `adk web` demo with Q1 to Q13 and record a short checklist in `eval/runs/<date>-demo.md` covering tool calls seen, citations present, and the Q13 refusal.

**Documentation**

27. `[new file: README.md]` Four parts: what PolicyPulse RAG is; how to run it (a short form of the runbook); how to test it (unit, live, eval); where the design lives (this plan, the diagram). Embed the Mermaid diagram from the next step.
28. Run `/axis-diagram` with the data-flow diagram from the architecture section as the brief: two lanes (query and ingestion), Vertex AI services on the right, ADC trust crossings marked. It writes the editable draw.io and Mermaid files to `.axis/diagrams/`. Test impact: none.
29. `[.axis/context/glossary.md:15-17]` Replace the TODO examples with: **Cite label** (the `Cite as:` string a block carries and the agent copies), **Breadcrumb block** (one rendered citation unit), **Corpus** (`policypulse-5docs-corpus`), **Source document** (one of the five files in `docs/`), **Registration API** (the external Customer Registration API spec, owned by another system), **Acceptance case** (one of the 13 eval cases). Test impact: none.

## Acceptance criteria

- [ ] `pytest -m "not live"` passes locally and in GitHub Actions with no GCP credentials and no network access, in random order, in under 60 s of test time.
- [ ] `python scripts/ingest_corpus.py --render-only` writes five files to `build/corpus/`, makes no GCP call, and passes the contract gate for all five documents.
- [ ] A first `python scripts/ingest_corpus.py` leaves exactly one `policypulse-5docs-corpus` with five ACTIVE files and writes `RAG_CORPUS_RESOURCE_NAME` to `.env`. A second run uploads nothing and leaves `.env` byte-identical.
- [ ] `pytest -m live tests/live` finds each expected label in the top 10 for Q1 to Q12.
- [ ] In `adk web`, every answer to Q1 to Q12 follows at least one `search_policy_documents` call and carries inline citations; Q13 returns exactly the refusal sentence.
- [ ] `adk eval policypulse_rag eval/policypulse_evalset.json --num_runs 3` passes all 13 cases.
- [ ] Git history shows the eval set before the first agent commit, each unit test commit before its implementation commit, and `eval/runs/` holds the red baseline and the green final run.
- [ ] `.axis/diagrams/` holds the draw.io and Mermaid architecture diagram, and `README.md` embeds the Mermaid version.
- [ ] All existing tests still pass. There are none today, so this means the new suite stays green.

## Test plan

Failing-first unit tests, grouped by file. Each test is arrange, act, assert and is named for the behavior it checks.

**`tests/unit/test_evalset_contract.py`**

1. **eval set validates as an ADK EvalSet.** Setup: read `eval/policypulse_evalset.json`. Expected: `EvalSet.model_validate_json` succeeds.
2. **holds the 13 acceptance cases in order.** Expected: eval ids `q01_...` to `q13_...`, each matching `^[a-zA-Z0-9_]+$`.
3. **each case asks its question verbatim.** Setup: a table of the 13 question strings. Expected: `user_content` text equals the table entry.
4. **each case expects the retrieval tool.** Expected: every `tool_uses` names `search_policy_documents`, with two entries for Q12 and one for the rest.
5. **every case rubric is typed for the final-response judge.** Expected: each rubric `type` equals `FINAL_RESPONSE_QUALITY`.
6. **the Q13 reference is the refusal sentence.** Expected: equals "The provided reference documents do not cover this topic."
7. **test_config validates and sets the agreed criteria.** Expected: `EvalConfig.model_validate_json` succeeds; the trajectory criterion uses `IN_ORDER` with `ignore_args`; the rubric, hallucination and response-match criteria are present.

**`tests/unit/test_blocks.py`**

1. **renders heading, cite line, body and end line.** Expected: exact markdown for one block.
2. **splits a block over 350 words at sentence boundaries.** Expected: parts of 350 words or fewer, each with the same label and breadcrumb.
3. **every 600-word window carries a label marker** (Hypothesis, random block lists). Expected: a `Cite as:` or `End of` line in every window.
4. **rejects a block with an empty label.** Expected: `ValueError`.

**`tests/unit/test_split_gdpr.py`**

1. **labels Article 33 paragraph 1 with its title in the breadcrumb.** Expected: label `GDPR Art. 33(1)`; breadcrumb holds the chapter, section and article title.
2. **labels points under a paragraph.** Expected: `GDPR Art. 5(1)(c)` contains "limited to what is necessary".
3. **labels Article 4 definitions.** Expected: `GDPR Art. 4(1)` and `GDPR Art. 4(2)`.
4. **labels recitals in sequence.** Expected: `GDPR Recital 85`, `GDPR Recital 86`.
5. **drops a footnote that breaks the recital sequence.** Expected: no block contains the footnote text.
6. **strips Official Journal running headers.** Expected: no block contains "Official Journal of the European Union".
7. **keeps Article 83 paragraphs 4 and 5 in separate blocks.** Expected: the 10 000 000 EUR text appears only under `GDPR Art. 83(4)`, and the 20 000 000 EUR text only under `GDPR Art. 83(5)`.

**`tests/unit/test_split_ncsp.py`**

1. **labels each numbered objective.** Expected: `NCSP 2013, Objective 8` contains "500,000".
2. **labels strategy paragraphs with the strategy title.** Expected: `NCSP 2013, Strategy E` blocks; the breadcrumb holds the strategy title.
3. **keeps Objective 10 separate from Objective 9.** Expected: "storage" and "transit" appear under Objective 10 only.

**`tests/unit/test_split_hipaa.py`**

1. **labels the minimum necessary section with heading and page.** Expected: the label starts `HIPAA Privacy Rule Summary, ` and ends with the fixture page.
2. **separates criminal from civil penalties.** Expected: "$250,000" appears only under the Criminal Penalties label.
3. **fails when an expected heading is missing.** Setup: heading list with an extra entry. Expected: `ContractError` naming the heading.

**`tests/unit/test_split_road_safety.py`**

1. **labels unnumbered opening text as Introduction.** Expected: `Road Safety Policy, Introduction`.
2. **labels numbered sections.** Expected: the Fund text sits under its numbered label.

**`tests/unit/test_split_registration_api.py`**

1. **builds labels from the heading path.** Expected: `Registration API, Fuzzy screening > Timeout`.
2. **ignores `#` lines inside fenced code.** Expected: no block starts inside the code fence.
3. **splits a numbered-heading PDF text the same way.** Expected: the same labels as the markdown form for equivalent headings.

**`tests/unit/test_extract.py`**

1. **joins wrapped lines inside a paragraph.** Expected: one line per paragraph.
2. **removes a line-end hyphen only before a lowercase letter.** Expected: "pro-\ncessing" becomes "processing"; "E-\nGovernance" stays hyphenated.
3. **strips lines matching the document's header patterns.** Expected: the header lines are removed and body lines are untouched.

**`tests/unit/test_documents.py`**

1. **registry lists five documents with distinct ids and citation names.**
2. **reports every missing source file.** Setup: an empty temp dir. Expected: a usage error listing all five names.
3. **accepts the API spec as .md or .pdf and rejects both together.**
4. **contract gate fails when a required label is missing.** Setup: GDPR blocks without Article 33. Expected: `ContractError` naming `GDPR Art. 33`.

**`tests/unit/test_corpus_sync.py`** (`FakeRagClient`, fake clock)

1. **creates the corpus when none exists**, with the display name and the text-embedding-005 endpoint.
2. **reuses the single matching corpus** and makes no create call.
3. **fails when two corpora share the display name** and lists both names.
4. **fails on an embedding-model mismatch** with a message suggesting `--recreate`.
5. **recreate deletes files, then the corpus, then creates a new one.** Expected: the fake's call log order.
6. **uploads every missing document with 1024/200 chunking.**
7. **a second run with unchanged documents uploads nothing.**
8. **a changed document uploads first and deletes the old file after ACTIVE.**
9. **cleans duplicates left by an interrupted run.**
10. **retries one ERROR file once, then fails with its status.**
11. **times out waiting for ACTIVE** (fake clock), naming the file.
12. **reports stray files and leaves them.**
13. **content hash changes when chunk settings change.**

**`tests/unit/test_dotenv_file.py`**

1. **creates the file when missing.**
2. **replaces an existing value and keeps other lines and comments.**
3. **a second identical write leaves the file byte-identical.**

**`tests/unit/test_ingest_cli.py`**

1. **render-only writes five markdown files and never builds a client.**
2. **missing GOOGLE_CLOUD_PROJECT exits 2 with a message.**
3. **missing source files exit 2 and list them.**
4. **a successful sync writes RAG_CORPUS_RESOURCE_NAME to the env file.**

**`tests/unit/test_agent_wiring.py`**

1. **root agent is named policypulse_rag and uses POLICYPULSE_MODEL, defaulting to gemini-2.5-flash.** Setup: monkeypatched env and `importlib.reload`.
2. **has exactly one tool, named search_policy_documents, matching the eval set's expected tool.**
3. **targets the corpus from RAG_CORPUS_RESOURCE_NAME with top_k 10 and threshold 0.6.** Expected: read from `tool.vertex_rag_store`.
4. **declares the tool to Gemini as a function.** Setup: `LlmRequest(model="gemini-2.5-flash")`; await `process_llm_request`. Expected: one function declaration named `search_policy_documents` and no `retrieval` entry in `config.tools`. Adjust the assertion to the shape `LlmRequest.append_tools` produces.
5. **stock VertexAiRagRetrieval attaches server-side retrieval for Gemini** (characterization). Expected: a `retrieval` tool and no function declaration. When an ADK upgrade breaks this test, re-check whether the subclass is still needed.
6. **missing RAG_CORPUS_RESOURCE_NAME raises with the ingest command in the message.**
7. **sets temperature 0.**

**`tests/unit/test_prompts.py`**

1. **requires a search before every answer.** Expected: Rule 1 text present.
2. **shows the citation format with an example label per document, each matching that document's label regex.**
3. **contains the refusal sentence verbatim, equal to the eval set's Q13 reference.**
4. **instructs one search per document for cross-document questions.**
5. **separates HIPAA minimum necessary from GDPR data minimisation.**
6. **contains no curly braces.**

**`tests/live/test_retrieval_live.py`** (marked `live`, manual)

1. **expected label in the top 10 for each question** (parameterized over Q1 to Q11 and Q12's four sub-queries). The test prints distances.
2. **records the best Q13 distance.** Informational; it never fails.

## Risks & rollback

- **Risk (Major):** `gemini-2.5-flash` is retired or not served in the chosen region. ADK 2.14.1 already defaults to `gemini-3.5-flash` (observed). → **Mitigation:** runbook preflight step 4; switch through `POLICYPULSE_MODEL` (`gemini-2.5-pro`, or `gemini-3.5-flash` with the reviewer's agreement) and update `judge_model` in `test_config.json`.
- **Risk (Major):** the RAG Engine region is restricted for this project. → **Mitigation:** preflight step 3; set `RAG_LOCATION=europe-west4` and re-run the ingest, which creates a new corpus in that region and leaves the old one untouched.
- **Risk (Major):** the subclass depends on ADK's `process_llm_request` hook and on `run_async` staying in place. → **Mitigation:** exact pin to 2.14.1; the characterization test fails first on any upgrade that changes the parent's behavior.
- **Risk (Major):** a splitter misreads the real PDF text, which yields wrong labels and therefore wrong citations. → **Mitigation:** the contract gate stops the run before upload; each fix starts with a failing fixture case; `--render-only` output is human-readable.
- **Risk (Minor):** the Q10 facts may be absent from the supplied Road Safety Policy PDF (UNVERIFIED). → **Mitigation:** step 21 checks the text; if the facts are absent, the reviewer decides whether Q10's expected answer changes. The agent must not supply them from memory.
- **Risk (Minor):** Markdown uploads are rejected. → **Mitigation:** write the same content as `.txt` and change the display-name suffix.
- **Risk (Minor):** the service ignores the chunking field in `rag_file_transformation_config`. → **Mitigation:** none cheap; the per-file chunk configuration cannot be read back. The labels repeat every 350 words, so citations survive any chunk size of at least about 500 tokens.
- **Risk (Minor):** judge nondeterminism flips a case. → **Mitigation:** `num_samples` 3, `--num_runs 3`, and `pass_rate` 0.66.
- **Risk (Minor):** cost. Each eval run makes 13 agent conversations plus judge calls (3 rubric samples and one hallucination pass per case), multiplied by `--num_runs`. The RAG-managed database may bill while provisioned (UNVERIFIED). → **Mitigation:** run the full gate only at milestones; tear down after the demo.
- **Risk (Minor):** the Customer Registration API spec belongs to another system, so a committed copy here would drift from its source (core-repository). → **Mitigation:** gitignored by default; `docs/SOURCES.md` records its sha256; commit it only with the owning team's agreement.
- **Risk (Nit):** the "No matching result" tool response includes the corpus resource name, which contains the project id. → **Mitigation:** committed eval summaries exclude raw tool responses.
- **Rollback:** nothing is deployed; the agent runs locally. Revert the offending commits. To remove cloud state, delete the corpus files and then the corpus in the console, and delete the `RAG_CORPUS_RESOURCE_NAME` line from `.env`.

## Out of scope

- Writing, editing or validating the Customer Registration API spec. This repo only ingests a supplied copy.
- Deployment beyond local `adk web`: Agent Engine, Cloud Run, authentication, multi-user sessions.
- CI running live `adk eval` or the live retrieval tests.
- The `adk web` Eval tab, which reads eval sets from `policypulse_rag/*.evalset.json`. This plan keeps the eval set at `eval/policypulse_evalset.json`, as the brief specifies.
- Multi-turn conversation evaluation, languages other than English, and documents beyond the five.
- Hybrid search, reranking, and per-document metadata filters (see Left unbuilt).

---

## Execution log — 2026-11-19

**Executed:** every offline step. Steps 1, 2, 4 and 5 were already in the working tree and match the plan. The unit suite (145 tests) and `ruff check .` pass in random order in about 13 seconds on Python 3.12.16 with the pinned dependencies. The machine had only Python 3.14 and no pip, so the tests ran from a 3.12 virtual environment that `uv` created in the session scratch directory, outside the repository.

**Not done, and why**

- **Step 3, `.env.example`:** the project permission rules deny writes to `.env.*`, so the file does not exist. AGENTS.md and the README refer to it. Its content is the six variables in the environment table, each with one comment line.
- **Step 6, API spec and URLs:** `docs/` holds the four public PDFs, copied from `/mnt/c/files/` under the registry file names. The Customer Registration API spec is not supplied, so `--render-only` exits 2 and names the missing file, as designed. The official download URLs stay an open question in `docs/SOURCES.md`.
- **Steps 9, 21, 25 and 26, live runs:** they need Application Default Credentials and a Google Cloud project. The baseline eval run is recorded as pending in `eval/runs/2026-11-19-baseline.md`. Step 21 is done as far as `--render-only` goes on the four real PDFs: every contract passes, and the Q10 facts are in the Road Safety PDF. The two ingest runs, the live recall run, the `adk eval` runs and the `adk web` checklist remain.
- **Red baseline in git history:** the working tree holds the final agent, so the tool-less baseline agent exists only if the commits are sliced. Commit the eval set and the baseline `agent.py` before the rest, then run the baseline eval at that commit.

**Deviations from the plan, each driven by the real PDFs**

- **GDPR footnotes** are dropped by position: every page ends with the Official Journal footer and the footnotes follow it. The recital-sequence rule alone fails on page 1, where footnote `(4)` continues the sequence. Recitals keep the sequence check, and the first `(n)` line starts it.
- **Line-end hyphens:** a soft hyphen is removed and the halves are joined, and an ASCII hyphen is kept. The PDFs break words with soft hyphens and use ASCII hyphens only inside compounds such as "non-workforce", which the plan's rule would corrupt.
- **NCSP labels** are finer than the plan's examples: `NCSP 2013, Objective 8`, `NCSP 2013, Strategy E, item 2`, `NCSP 2013, Preamble, para 3`. A strategy without items, N, is `NCSP 2013, Strategy N`.
- **Road Safety Policy** has unnumbered titled sections, so the splitter cuts at a registry of 14 headings and labels blocks `Road Safety Policy, <heading>`, plus `Road Safety Policy, Introduction`. A line that repeats an earlier line is dropped, which removes a layout echo on page 2.
- **HIPAA labels** carry the PDF page index, as the plan's rule says: Minimum Necessary is `p. 12` and Criminal Penalties is `p. 20`. The plan's examples used printed page numbers. The End Notes are not cited.
- **Rubrics for Q10 and Q11** note the document's own wording: the date `15.03.2010`, the committee name spelled `Sunder`, and `gasoline` where the reference answer says petrol.
- **Prompt example labels** follow the real label formats, with `NCSP 2013, Strategy E, item 2` added.
- **Unit tests** set a placeholder `RAG_CORPUS_RESOURCE_NAME` in `tests/unit/conftest.py`, because `policypulse_rag/agent.py` raises at import when the value is missing.

**Real-file results:** GDPR 947 blocks (173 recitals, 99 articles), HIPAA summary 72, NCSP 82, Road Safety Policy 15. The block-count ranges in `documents.py` come from these runs. The Registration API entry has no required labels until the spec is supplied.

**Diagram, step 28:** the `axis-diagram` agent wrote `.axis/diagrams/policypulse-rag.drawio` and `.axis/diagrams/policypulse-rag.mmd`, and the README embeds the Mermaid version. Neither file has been rendered, so open the draw.io file once to confirm the Vertex AI icon shapes display.
