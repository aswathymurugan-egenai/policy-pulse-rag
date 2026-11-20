# PolicyPulse RAG

A question-answering agent built on Google ADK and Vertex AI RAG Engine. It answers from five policy and specification documents, cites the article, objective, or section behind each claim, and replies with a fixed refusal sentence when the documents do not cover a question.

The five documents are the GDPR (Regulation (EU) 2016/679), the HHS summary of the HIPAA Privacy Rule, India's National Cyber Security Policy 2013, India's National Road Safety Policy (2010), and the Customer Registration API specification. A reviewer opens `adk web`, asks a question such as "How quickly must a personal data breach be reported under GDPR?", and gets an answer with inline citations like `[GDPR Art. 33(1)]`.

## How it works

```mermaid
flowchart LR
  subgraph LOCAL["LOCAL MACHINE"]
    direction TB

    subgraph QUERY["QUERY PATH (runs on every question)"]
      direction LR
      user(["1. User<br/>browser"])
      runner["2. adk web / Runner<br/>FastAPI, localhost:8000"]
      sessions[("Session store<br/>policypulse_rag/.adk/")]
      agent["3. LlmAgent 'policypulse_rag'<br/>agent.py, instruction in prompts.py<br/>answers from returned chunks only"]
      retr["4. PolicyDocsRetrieval<br/>subclass of ADK VertexAiRagRetrieval<br/>similarity_top_k=10<br/>vector_distance_threshold=0.6"]
      answer["5. Answer contract<br/>inline citations such as [GDPR Art. 33(1)]<br/>otherwise exactly: 'The provided reference<br/>documents do not cover this topic.'"]
    end

    subgraph INGEST["INGESTION PATH: python scripts/ingest_corpus.py (safe to re-run)"]
      direction LR
      docs["1. docs/ (immutable raw layer)<br/>GDPR, HIPAA summary, NCSP 2013,<br/>Road Safety 2010 PDFs;<br/>Registration API spec (md or PDF,<br/>other system, not yet supplied)"]
      extract["2. Extract text<br/>pypdf per page;<br/>markdown read as is"]
      split["3. Per-document splitter<br/>citation blocks:<br/>label, breadcrumb, text"]
      render["4. Render<br/>build/corpus/#lt;doc_id#gt;.md<br/>breadcrumb heading, Cite as: line,<br/>End of line per block"]
      gate["5. Contract gate<br/>required labels present,<br/>block counts in range;<br/>failure stops the run before any cloud call"]
      sync["6. Corpus sync<br/>find or create corpus;<br/>upload changed files<br/>#lt;doc_id#gt;__#lt;sha12#gt;.md, unchanged skipped;<br/>wait for ACTIVE"]
      env[".env (repo root)<br/>RAG_CORPUS_RESOURCE_NAME,<br/>read by the agent at startup"]
    end

    subgraph EVAL["EVALUATION (optional)"]
      eval["adk eval policypulse_rag<br/>eval/policypulse_evalset.json<br/>runs the 13 acceptance cases against the agent"]
    end
  end

  subgraph GCP["GOOGLE CLOUD: VERTEX AI"]
    direction TB
    gemini["Gemini 2.5 Flash (Vertex AI)<br/>generateContent, region GOOGLE_CLOUD_LOCATION<br/>Gemini 2.5 Pro: env switch POLICYPULSE_MODEL"]
    rag["Vertex AI RAG Engine<br/>RetrieveContexts, region RAG_LOCATION<br/>corpus policypulse-5docs-corpus, 5 documents<br/>embeddings text-embedding-005<br/>1024-token chunks, 200 overlap"]
    judge["Vertex AI<br/>rubric-based judging of the 13 cases"]
  end

  legend["LEGEND<br/>Thick orange arrow labeled ADC = trust crossing from the local machine<br/>into Google Cloud, authenticated with Application Default Credentials, no key files.<br/>Thin arrow = data or control flow. Dashed = session storage or startup config read."]

  %% Query path (edges 0 to 6)
  user -->|"HTTP localhost:8000"| runner
  runner -->|"streamed answer"| user
  runner -.-|"sessions"| sessions
  runner -->|"user message"| agent
  agent -->|"cited answer or refusal"| runner
  agent -->|"search_policy_documents(query)<br/>one to several calls per question"| retr
  retr -->|"up to 10 chunk texts<br/>with Cite as: labels"| agent

  %% ADC crossings (edges 7 and 8)
  agent <==>|"ADC: generateContent request;<br/>function calls and answer text return"| gemini
  retr <==>|"ADC: RetrieveContexts(query);<br/>chunks return"| rag

  %% Ingestion path (edges 9 to 16)
  docs -->|"files"| extract
  extract -->|"page text"| split
  split -->|"blocks"| render
  render -->|"rendered md"| gate
  gate -->|"gate passed"| sync
  sync <==>|"ADC: upload changed files;<br/>corpus ACTIVE"| rag
  sync -->|"writes corpus name"| env
  env -.->|"read at startup"| retr

  %% Evaluation (edge 17)
  eval <==>|"ADC: rubric-based judging"| judge

  classDef query fill:#dae8fc,stroke:#6c8ebf,color:#1a1a1a;
  classDef ingest fill:#d5e8d4,stroke:#82b366,color:#1a1a1a;
  classDef cloud fill:#e1d5e7,stroke:#9673a6,color:#1a1a1a;
  classDef evalc fill:#fff2cc,stroke:#d6b656,color:#1a1a1a;
  classDef note fill:#ffffff,stroke:#999999,color:#1a1a1a;
  class user,runner,sessions,agent,retr,answer query;
  class docs,extract,split,render,gate,sync,env ingest;
  class gemini,rag,judge cloud;
  class eval evalc;
  class legend note;

  style QUERY fill:#f5f9ff,stroke:#6c8ebf,stroke-dasharray:5 5;
  style INGEST fill:#f6fbf4,stroke:#82b366,stroke-dasharray:5 5;
  style EVAL fill:#fffbee,stroke:#d6b656,stroke-dasharray:5 5;
  style LOCAL fill:#ffffff,stroke:#666666,stroke-dasharray:5 5;
  style GCP fill:#faf6fc,stroke:#9673a6,stroke-dasharray:5 5;

  linkStyle 7,8,14,17 stroke:#d79b00,stroke-width:3px,color:#8a5a00;
  linkStyle 2,16 stroke:#666666,stroke-dasharray:5 5;
```

The same diagram is in `.axis/diagrams/policypulse-rag.drawio` as an editable draw.io file.

The ingest renders each source document into citation blocks. Every block carries a breadcrumb heading, a `Cite as:` label, and an `End of` label, so every chunk the RAG engine cuts from a file still names its source. The agent calls one tool, `search_policy_documents`, as many times as a question needs, and copies the labels into its answer.

## Run it

Setup needs Python 3.11 to 3.13, a Google Cloud project with billing and the Vertex AI API enabled, and `roles/aiplatform.user` for your account. The agent authenticates with Application Default Credentials, so no key file exists anywhere.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                       # fill in GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, RAG_LOCATION
gcloud auth application-default login
gcloud auth application-default set-quota-project "$GOOGLE_CLOUD_PROJECT"
```

Put the five source files in `docs/` under the names listed in `docs/SOURCES.md`. The Customer Registration API spec belongs to another system and stays out of git; place your copy at `docs/customer_registration_api_spec.md` (or `.pdf`).

```bash
python scripts/ingest_corpus.py --render-only   # writes build/corpus/*.md, no cloud call
python scripts/ingest_corpus.py                 # creates the corpus, uploads, writes RAG_CORPUS_RESOURCE_NAME to .env
python scripts/ingest_corpus.py                 # second run prints five "skip" lines
adk web                                         # run from the repo root, open http://localhost:8000
```

Choose `policypulse_rag` in the agent picker. Each answer shows its `search_policy_documents` calls in the event trace. Set `POLICYPULSE_MODEL=gemini-2.5-pro` in `.env` to use Pro. `python scripts/ingest_corpus.py --recreate` rebuilds the corpus from scratch. After the demo, delete the corpus in the Google Cloud console under Vertex AI, RAG Engine.

## Test it

| Command | What it runs |
| --- | --- |
| `pytest -m "not live"` | The unit suite. It needs no cloud access or network, runs in random order, and stays under 60 seconds. |
| `ruff check .` | Lint. |
| `pytest -m live tests/live -s` | Retrieval recall against the live corpus. It needs ADC and a populated corpus, and prints the distance of each expected chunk. |
| `adk eval policypulse_rag eval/policypulse_evalset.json --print_detailed_results` | The 13 acceptance questions, scored by rubrics, tool trajectory, and a hallucination check. Add `--num_runs 3` for the final gate. |

CI runs the lint and the unit suite only.

## Where things live

| Path | Holds |
| --- | --- |
| `policypulse_rag/` | The ADK agent: `agent.py` (the agent and its retrieval tool) and `prompts.py` (the instruction and refusal sentence). |
| `scripts/policypulse_ingest/` | The ingest: extraction, one splitter per document, the contract gate, and the idempotent corpus sync. |
| `docs/` | The source documents and `SOURCES.md` with their hashes. |
| `eval/` | The acceptance eval set, the scoring criteria, and `runs/` with a summary of each live run. |
| `tests/` | `unit/` for CI, `live/` for manual runs, `fixtures/` cut from the source documents. |
| `.axis/plans/policypulse-rag.md` | The design: approach, chunking strategy, retrieval settings, acceptance matrix, and runbook. |
| `.axis/diagrams/` | The architecture diagram as editable draw.io and Mermaid files. |

## Contributing

Write the failing test first and commit it ahead of its implementation. Commit subjects follow `type(scope): summary`, with scopes such as `agent`, `ingest`, `eval`, `ci`, and `docs`. Run `pytest -m "not live"` and `ruff check .` before pushing.
