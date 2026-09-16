# RepoMind — Technical Requirements Document

## 1. Architecture choice
Use a monorepo with a web application and Python API:

- Frontend: Next.js + TypeScript
- Backend: FastAPI + Python
- Database: PostgreSQL with pgvector
- Vector search: pgvector cosine similarity
- Lexical search: PostgreSQL full-text search / trigram support where useful
- ORM/migrations: SQLAlchemy + Alembic
- Validation: Pydantic
- HTTP client: httpx
- GitHub integration: GitHub REST API
- Embedding provider: provider interface; default zero-cost local embedding implementation where practical, optional hosted implementation through environment configuration
- LLM provider: provider interface; Gemini-compatible implementation for hosted inference, plus deterministic mock provider for tests
- Reranker: provider interface; local cross-encoder implementation where deployment resources allow; otherwise configurable fallback
- Frontend styling: Tailwind CSS or CSS modules, but with a custom restrained design system described in `09-UI-UX-SPEC.md`
- Testing: pytest, pytest-asyncio, Playwright, Vitest/Jest as appropriate
- Packaging: Docker + docker-compose for local development
- CI: GitHub Actions

## 2. Why PostgreSQL + pgvector
Keep relational metadata and embeddings in one system. This simplifies local development, transactions, migrations, filters, joins, and deployment. pgvector supports exact and approximate nearest-neighbor search plus cosine distance and HNSW indexes. citeturn266142search1

## 3. Why GitHub REST API
The system only needs public repository metadata, content/tree information, issues/PR data as an optional extension point, and authenticated rate-limit headroom when a token is configured. GitHub provides repository contents endpoints and authenticated requests receive materially higher limits than unauthenticated requests. citeturn266142search0turn266142search2

## 4. Provider abstraction
Create interfaces:

```text
EmbeddingProvider
  embed_documents(texts) -> vectors
  embed_query(text) -> vector

LLMProvider
  generate(messages, context, stream) -> response/stream

Reranker
  rank(query, candidate_chunks) -> scored_chunks
```

The rest of the system must not depend directly on SDK-specific model classes.

## 5. Default zero-cost development strategy
- PostgreSQL/pgvector runs locally via Docker.
- Local embeddings may use a small Sentence Transformers model.
- LLM calls use a configured provider only when a key is present.
- Tests use a fake embedding provider and fake LLM.
- No paid observability platform is required.
- External API usage is opt-in via environment variables.

## 6. Configuration
Use environment variables with `.env.example`. Example categories:

```text
APP_ENV
API_BASE_URL
DATABASE_URL
GITHUB_TOKEN
GITHUB_API_URL
LLM_PROVIDER
LLM_API_KEY
LLM_MODEL
EMBEDDING_PROVIDER
EMBEDDING_MODEL
RERANKER_PROVIDER
REDIS_URL (optional)
CORS_ORIGINS
RATE_LIMIT_* 
MAX_*_LIMITS
```

No provider key should be required to run unit tests.

## 7. Repository/package structure
```text
repomind/
  apps/
    web/
    api/
  packages/
    shared-types/
  infra/
    docker/
    migrations/
  evals/
    dataset.jsonl
    README.md
  docs/
  .github/
    workflows/
  docker-compose.yml
  Makefile
  README.md
  .env.example
```

A simpler structure is acceptable when it improves maintainability, but separation between web, API, docs, and evaluation assets must remain clear.

## 8. Important engineering decisions
- Do not introduce a message queue for MVP unless required by a concrete reliability issue.
- Use background tasks for ingestion in local mode only if the framework implementation remains robust; otherwise implement a job table with status transitions.
- Prefer database-backed job status over adding Redis solely for job tracking.
- Keep ingestion idempotent.
- Make all limits configurable.
- Do not silently truncate user questions or source content.
- Do not log full source repositories or secrets by default.

## 9. Current API/reference constraints
GitHub REST endpoints are rate-limited and subject to secondary limits, so ingestion must be bounded, authenticated when a token is configured, and backoff-aware. citeturn266142search2
