# Architecture notes

The [reference specifications](spec/) describe the intended product. This document describes the implementation in this repository.

## Ingestion

`POST /api/v1/repositories/ingest` validates a canonical GitHub URL and resolves public repository metadata. It creates an `ingestion_jobs` row and runs a background job in the API process. The job resolves the selected ref to a commit, requests the recursive Git tree, applies file and total size limits, fetches eligible blobs, normalizes UTF-8 text, chunks it with line ranges, creates embeddings, and stores everything in PostgreSQL. Job progress is committed as it advances through fetching, parsing, embedding, and indexing. A failed snapshot is never marked complete. On process startup, the single-process API retries interrupted jobs.

The snapshot fingerprint includes repository, ref, commit SHA, chunk version, and embedding model. A completed fingerprint is reused. When a new commit contains a file with a previously indexed path and GitHub blob SHA, the job copies its stored source and vectors instead of fetching and embedding it again.

## Retrieval, evidence gating, and answers

The query endpoint selects the latest completed snapshot for its repository. It embeds the question, runs pgvector cosine and PostgreSQL full-text searches with the snapshot filter, fuses their ranks with RRF, and reranks the result. The default token-overlap reranker needs no additional model. A local CrossEncoder option is available through configuration. Context assembly removes overlapping ranges and caps the evidence budget. Each evidence item has an opaque citation ID tied to a stored source file and line range.

Before generation, a deterministic evidence gate combines meaningful query-term coverage, top dense similarity, dense/lexical rank agreement, top-evidence token overlap, and candidate concentration. Passing requires a minimum term match, a configurable combined score, and multiple independent signals. Failure returns the standard insufficient-evidence response with no citations and does not construct or call a generation provider. Thresholds live in `Settings`; increasing them favors precision and abstention, while decreasing them favors recall. Short identifiers and embedding-model calibration remain known limitations.

The ordered generation chain is `gemini-3.8-flash` → `gemini-3.7-flash` → deterministic grounded fallback. Each hosted model receives one bounded attempt. The Gemini providers use the current Interactions API structured-output contract without legacy sampling parameters. Transient HTTP/network failures advance to the next provider. Shared authentication or malformed-request failures stop further hosted attempts, while a model-specific invalid configuration can advance to the secondary model. The deterministic provider uses templates and selected evidence lines; it is not an LLM.

Gemini receives only selected, explicitly untrusted evidence and must return a strict JSON answer with citation IDs. The API removes IDs and inline markers absent from the selected evidence. It builds GitHub links from the stored commit SHA, never from model text. This validation controls citation identity; it cannot prove every generated sentence is correct, so the UI also exposes the underlying source.

Every query records provider attempts, the selected provider, fallback state, safe failure categories, evidence-gate signals, and retrieval/generation/total latency in the message metadata. Logs contain those safe categories and timings only; raw provider response bodies, authorization headers, prompts, API keys, and repository context are excluded.

## Data and operations

Alembic creates the relational tables, GIN full-text index, and pgvector HNSW cosine index. Foreign keys cascade from repositories to snapshots, files, chunks, sessions, and messages. The `delete_repository` data-layer function performs a full cascade. `/health/live` checks process response; `/health/ready` checks database access and vector dimension. The migration uses a 384-dimensional vector column for the default embedding model; changing models to a different dimension requires a matching migration.

GitHub HTTP calls use bounded retries. Each hosted generation model receives one bounded call before the chain advances. The API accepts only GitHub repository URLs, skips binary and oversized files, and never executes repository content. Secrets are represented as secret settings, stay on the server, and are never placed in browser-visible environment variables. The public POST rate limit is per IP within one API process. For production with multiple workers or replicas, the background runner and rate limit need a shared worker and shared limiter. The database job table provides the transition point for that change.
