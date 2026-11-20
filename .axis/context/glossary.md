# Glossary

Per-repo domain vocabulary. axis seeds this stub once on first install, then
never touches it again — fill it in and commit it so every agent shares the same
words for this project's concepts (domain terms, acronyms, internal service
names, status codes, "what we mean by X here").

Agents read this on demand (linked from `AGENTS.md`); keep entries short. Define the
**canonical** word for each concept and say what it **is** (not what it does); if the
team uses rival synonyms, name the one we use and which to avoid (e.g. "we say
_Member_ — not _user_ or _patient_"). Project-specific terms only — skip generic
industry words an agent already knows.

- **Cite label** — the string on a block's `Cite as:` line, such as `GDPR Art. 33(1)`. The agent copies it in square brackets after each claim it supports.
- **Breadcrumb block** — one rendered citation unit: a breadcrumb heading, a `Cite as:` line, the text, and an `End of` line. It is the smallest piece of a document a citation can point at.
- **Corpus** — the Vertex AI RAG Engine corpus `policypulse-5docs-corpus`, which holds the five rendered source documents.
- **Source document** — one of the five files in `docs/` that the agent answers from. Each has a doc id, a citation name, and its own splitter.
- **Registration API** — the Customer Registration API specification. Another system owns it, so this repo ingests a supplied copy and never edits it. Its blocks use the citation name `Registration API`.
- **Acceptance case** — one of the 13 questions, Q1 to Q13, in `eval/policypulse_evalset.json`. Each carries a reference answer and rubrics, and the set is the gate for the agent.
- **Contract gate** — the check that runs on each document's blocks before anything is rendered or uploaded. It fails the ingest when a required label is missing or the block count is out of range.
- **PHI** — protected health information, the subject of the HIPAA Privacy Rule Summary. Do not use it for GDPR personal data.
