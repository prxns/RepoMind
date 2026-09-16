# RepoMind — Software Requirements Specification

## 1. Functional requirements

### FR-01 Repository validation
The system shall accept a public GitHub repository URL in canonical forms such as `https://github.com/{owner}/{repo}` and reject unsupported URLs with a useful validation error.

### FR-02 Repository discovery
The system shall resolve owner, repository name, default branch, and repository metadata.

### FR-03 File enumeration
The system shall enumerate repository files from the GitHub contents/tree APIs and filter by supported extensions, path rules, and maximum file size.

### FR-04 Content acquisition
The system shall fetch raw textual content for eligible files and retain enough metadata to map chunks back to their source.

### FR-05 Incremental ingestion
The system shall compute a repository snapshot identifier/ref plus file SHA metadata so unchanged content can be skipped on a future ingestion.

### FR-06 Chunk creation
The system shall generate deterministic chunks from source content, preserving path and line-range metadata.

### FR-07 Embedding
The system shall transform chunks into fixed-size vector embeddings through a provider abstraction.

### FR-08 Indexing
The system shall persist chunks, metadata, embeddings, and lexical-search data in PostgreSQL with pgvector.

### FR-09 Hybrid retrieval
The system shall combine vector similarity and lexical relevance into a single ranked candidate list.

### FR-10 Reranking
The system shall rerank the candidate set using an interchangeable reranker implementation.

### FR-11 Grounded generation
The system shall generate answers from retrieved context and instruct the model to abstain when context is insufficient.

### FR-12 Citations
The system shall return source references including repository, file path, and line range when known.

### FR-13 Session history
The system shall maintain the active repository session and recent query/answer history.

### FR-14 Streaming
The answer endpoint should support streaming model output when the configured provider supports it; a non-streaming fallback is required.

### FR-15 Health checks
The API shall expose liveness/readiness health endpoints that distinguish application health from dependency health.

### FR-16 Evaluation
The system shall include an evaluation runner for a versioned benchmark dataset.

### FR-17 Rate limiting
Public API endpoints shall have configurable per-IP rate limiting or a safe deployment-compatible equivalent.

### FR-18 Error handling
The API shall return structured errors with machine-readable codes and human-readable messages.

## 2. Non-functional requirements

### NFR-01 Security
Secrets must only be loaded from environment variables or deployment secret stores. No secret may be committed to source control.

### NFR-02 Reliability
Transient upstream failures must use bounded exponential backoff. Permanent failures must fail clearly without infinite retry loops.

### NFR-03 Determinism
Chunk IDs and document fingerprints must be deterministic for identical source content and configuration.

### NFR-04 Performance
The application should avoid redundant GitHub calls, embeddings, and database queries. Query-time retrieval should be bounded by configurable top-k values.

### NFR-05 Maintainability
Modules shall have single responsibilities with typed Python interfaces and strict TypeScript types.

### NFR-06 Testability
Core parsing, chunking, retrieval fusion, citation construction, and API validation shall be unit tested. End-to-end ingestion/query flows shall be integration tested with deterministic mocks where external services are unavailable.

### NFR-07 Portability
The backend must run in Docker and locally without cloud-specific dependencies. Database access must use standard PostgreSQL/pgvector.

### NFR-08 Accessibility
The frontend shall use semantic HTML, keyboard-accessible controls, visible focus states, adequate contrast, and readable code/source panels.

### NFR-09 Transparency
The UI must distinguish generated text from retrieved evidence and expose citations clearly.

## 3. Acceptance thresholds
- No critical-path endpoint may return unhandled 500 errors for expected bad input.
- Invalid GitHub URLs must fail before network-heavy ingestion.
- Unsupported/binary files must not be embedded.
- Citation metadata must survive chunk -> retrieval -> answer response.
- Evaluation runner must produce reproducible output for the checked-in benchmark fixtures.
