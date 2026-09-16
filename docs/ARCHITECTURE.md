# Architecture notes

The [reference specifications](spec/) describe the intended product. This document describes the implementation in this repository.

## Ingestion

`POST /api/v1/repositories/ingest` validates a canonical GitHub URL and resolves public repository metadata. It creates an `ingestion_jobs` row and runs a background job in the API process. The job resolves the selected ref to a commit, requests the recursive Git tree, applies file and total size limits, fetches eligible blobs, normalizes UTF-8 text, chunks it with line ranges, creates embeddings, and stores everything in PostgreSQL. Job progress is committed as it advances through fetching, parsing, embedding, and indexing. A failed snapshot is never marked complete. On process startup, the single-process API retries interrupted jobs.

The snapshot fingerprint includes repository, ref, commit SHA, chunk version, and embedding model. A completed fingerprint is reused. When a new commit contains a file with a previously indexed path and GitHub blob SHA, the job copies its stored source and vectors instead of fetching and embedding it again.

## Retrieval and answers

The query endpoint selects the latest completed snapshot for its repository. It embeds the question, runs pgvector cosine and PostgreSQL full-text searches with the snapshot filter, fuses their ranks with RRF, and reranks the result. The default token-overlap reranker needs no additional model. A local CrossEncoder option is available through configuration. Context assembly removes overlapping ranges and caps the evidence budget. Each evidence item has an opaque citation ID tied to a stored source file and line range.

The default extractive provider returns cited excerpts. The optional Gemini provider sends only selected, explicitly untrusted evidence and asks for a JSON answer with citation IDs. The API removes IDs and inline markers absent from the selected evidence. It builds GitHub links from the stored commit SHA, never from model text. This validation controls citation identity; it cannot prove every generated sentence is correct, so the UI also exposes the underlying source.

## Data and operations

Alembic creates the relational tables, GIN full-text index, and pgvector HNSW cosine index. Foreign keys cascade from repositories to snapshots, files, chunks, sessions, and messages. The `delete_repository` data-layer function performs a full cascade. `/health/live` checks process response; `/health/ready` checks database access and vector dimension. The migration uses a 384-dimensional vector column for the default embedding model; changing models to a different dimension requires a matching migration.

GitHub and model HTTP calls use bounded timeouts and retries. The API accepts only GitHub repository URLs, skips binary and oversized files, and never executes repository content. Secrets stay on the server. The public POST rate limit is per IP within one API process. For production with multiple workers or replicas, the background runner and rate limit need a shared worker and shared limiter. The database job table provides the transition point for that change.
