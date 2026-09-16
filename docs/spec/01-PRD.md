# RepoMind — Product Requirements Document

## 1. Product statement
RepoMind is a repository-aware knowledge engine that turns a GitHub repository into a searchable, source-grounded knowledge base. A user supplies a public GitHub repository URL, RepoMind ingests relevant code and documentation, builds a searchable index, and answers natural-language questions with citations to repository files and line ranges where available.

The product is not positioned as a generic chatbot. Its core value is **trustworthy repository understanding**: retrieval quality, source transparency, reproducibility, and useful technical answers.

## 2. Target user
Primary user: software developer, student, reviewer, or engineering team member who needs to understand an unfamiliar repository quickly.

Representative questions:
- Where is authentication implemented?
- What happens when a user creates an order?
- Which module owns database connections?
- Where are API errors transformed into HTTP responses?
- What tests cover the payment flow?
- What is the purpose of this configuration file?

## 3. MVP user journey
1. User opens RepoMind.
2. User enters a public GitHub repository URL.
3. System validates and normalizes the repository identifier.
4. System fetches repository metadata and eligible files.
5. System parses, chunks, embeds, and indexes content.
6. UI shows ingestion progress and final statistics.
7. User asks questions.
8. Retrieval returns relevant chunks using hybrid lexical + vector search.
9. Reranking orders candidates by relevance.
10. LLM generates an answer constrained by retrieved context.
11. UI renders the answer, citations, and retrieval metadata.
12. User can inspect cited source files and line ranges.

## 4. Core features
### 4.1 Repository ingestion
- Accept public GitHub URL.
- Support branch/ref selection when available; default to repository default branch.
- Fetch repository metadata.
- Recursively enumerate repository tree.
- Ignore binaries and excluded paths.
- Preserve path, language, size, SHA, and line boundaries.
- Ingest Markdown and common source/config files.
- Avoid committing or persisting raw GitHub credentials.
- Respect GitHub API rate limits and backoff on 403/429.

### 4.2 Chunking
- Chunk by logical file/code boundaries where practical.
- Preserve file path and start/end line numbers.
- Include metadata: repository, ref, language, file path, chunk sequence, SHA.
- Avoid splitting extremely small related code fragments unnecessarily.
- Keep chunk sizes configurable.

### 4.3 Retrieval
- Dense semantic retrieval using embeddings.
- Lexical retrieval using PostgreSQL full-text search.
- Merge candidates using reciprocal rank fusion or equivalent deterministic hybrid strategy.
- Optional reranking stage using a cross-encoder/provider abstraction.
- Apply repository/ref filters before final ranking.

### 4.4 Answer generation
- Answer only from retrieved repository context.
- Cite every substantive claim where evidence exists.
- Explicitly state when evidence is insufficient.
- Never fabricate file paths, symbols, line numbers, or behavior.
- Provide concise technical explanations by default.
- Support follow-up questions within the active repository session.

### 4.5 Observability and evaluation
- Record ingestion statistics.
- Record retrieval latency and generation latency.
- Record retrieval scores and top-k results for debug mode.
- Provide a small built-in evaluation dataset and runner.
- Calculate retrieval metrics and answer-groundedness metrics using deterministic or documented methods.
- Never display made-up quality percentages.

## 5. Non-goals for MVP
- Private repository OAuth installation.
- Multi-tenant enterprise billing.
- Fine-tuning a model.
- Autonomous code modification.
- Voice/chat multimodality.
- Large-scale distributed ingestion cluster.
- Full GitHub synchronization via webhooks.

The architecture should leave clear extension points for these later without implementing them now.

## 6. Success criteria
The project is successful when:
- A fresh clone can run locally with documented setup.
- A public repository can be ingested end-to-end.
- Questions return grounded answers with file/line citations.
- Retrieval can be inspected independently of generation.
- The evaluation suite runs reproducibly.
- Automated tests cover critical ingestion, retrieval, API, and security behavior.
- The application looks and feels like a serious developer tool, not a generic AI landing page.
- The repository includes architecture documentation and a clear demo workflow.

## 7. Product principles
1. Evidence before eloquence.
2. Fast path for the common developer question.
3. Every generated answer should be traceable to repository evidence.
4. Errors should be explicit and actionable.
5. Visual design should prioritize hierarchy, density, and usability over decoration.
