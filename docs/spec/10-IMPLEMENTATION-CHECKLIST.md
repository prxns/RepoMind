# RepoMind — Implementation Checklist / Definition of Done

## Project bootstrap
- [ ] Monorepo initialized.
- [ ] README and docs included.
- [ ] `.gitignore`, `.env.example` created.
- [ ] lint/format/type-check scripts configured.
- [ ] Docker Compose starts PostgreSQL with pgvector.

## Backend
- [ ] FastAPI app starts.
- [ ] Configuration module.
- [ ] SQLAlchemy models.
- [ ] Alembic migrations.
- [ ] Health endpoints.
- [ ] Structured error handler.
- [ ] Request IDs.
- [ ] Repository URL parser.
- [ ] GitHub client with retry/backoff/rate-limit awareness.
- [ ] File filters.
- [ ] Content fetcher.
- [ ] Chunker with line ranges.
- [ ] Embedding interface + implementation.
- [ ] Lexical search.
- [ ] Vector search.
- [ ] Hybrid fusion.
- [ ] Reranker interface + implementation.
- [ ] Context packer.
- [ ] LLM provider interface + implementation.
- [ ] Citation validation.
- [ ] Session/message persistence.
- [ ] Ingestion job state transitions.
- [ ] Rate limiting.

## Frontend
- [ ] Next.js app.
- [ ] Typed API client.
- [ ] Onboarding page.
- [ ] Ingestion status page/state.
- [ ] Repository session layout.
- [ ] Query composer.
- [ ] Answer renderer.
- [ ] Citation/source panel.
- [ ] Conversation history.
- [ ] Error/empty/loading states.
- [ ] Responsive and keyboard accessible.

## Evaluation
- [ ] Dataset fixtures.
- [ ] Retrieval benchmark runner.
- [ ] Baselines: lexical/vector/hybrid/hybrid+reranker.
- [ ] Metrics output.
- [ ] Evaluation README.

## Testing
- [ ] Unit tests for parsing/chunking.
- [ ] Unit tests for URL validation and file filtering.
- [ ] Unit tests for RRF/hybrid ranking.
- [ ] Unit tests for citation validation.
- [ ] API tests.
- [ ] Ingestion integration test using mocked GitHub API.
- [ ] Retrieval integration test using deterministic embeddings.
- [ ] Frontend component tests.
- [ ] One Playwright happy path.

## CI/CD
- [ ] Backend lint/type/test job.
- [ ] Frontend lint/type/test job.
- [ ] Build checks.
- [ ] No secret values committed.

## Documentation
- [ ] Setup instructions.
- [ ] Environment variables.
- [ ] Architecture diagram.
- [ ] API overview.
- [ ] Evaluation instructions.
- [ ] Known limitations.
- [ ] Deployment instructions.
- [ ] Screenshots/GIF placeholder paths documented for the user to add only after actual UI capture.

## Quality gates
The implementation is not complete if:
- UI is a generic AI landing-page template.
- Tests are placeholders.
- Metrics are hardcoded.
- Citations are decorative and not linked to real chunks.
- LLM output can invent paths/lines without validation.
- A clean clone cannot start locally.
- Core logic is duplicated across routes/services.
