# RepoMind — Software Design Specification

## 1. Logical components

### Web client
Responsibilities:
- repository onboarding form
- ingestion status
- query composer
- answer rendering
- citation/source inspection
- conversation history
- retrieval debug panel in development mode

### API
Responsibilities:
- HTTP contract and validation
- repository/job orchestration
- retrieval orchestration
- answer generation
- session state
- security/rate limiting

### Ingestion pipeline
```text
Repository URL
 -> normalize
 -> fetch metadata/tree
 -> filter files
 -> fetch content
 -> parse/normalize
 -> chunk
 -> fingerprint
 -> embed
 -> persist
```

### Retrieval pipeline
```text
Question
 -> normalize
 -> embed query
 -> vector search
 + lexical search
 -> RRF / hybrid fusion
 -> rerank
 -> context packing
 -> grounded prompt
 -> generation
 -> citation validation
 -> response
```

## 2. Ingestion state machine
```text
PENDING
  -> FETCHING
  -> PARSING
  -> EMBEDDING
  -> INDEXING
  -> COMPLETED

Any active state -> FAILED
```

Persist status, timestamps, counters, and a safe error code/message.

## 3. Repository snapshot model
A repository snapshot is identified by owner, name, ref, and a computed snapshot fingerprint. File-level SHA values are retained. Re-ingestion should skip unchanged files when possible.

## 4. Supported content
Initial allowlist should include common:
- Python, JavaScript, TypeScript, Java, Go, Rust, C/C++, C#, SQL, R
- HTML, CSS, JSON, YAML/YML, TOML, XML
- Markdown, MDX, plaintext
- shell scripts and Dockerfiles

Exclude by default:
- binaries/images/audio/video
- dependency/build directories (`node_modules`, `dist`, `build`, `.git`, virtualenvs, caches)
- lockfiles when they add noise, unless explicitly configured
- files exceeding configured size limit
- generated/minified files where identifiable

## 5. Chunking algorithm
Preferred order:
1. Split by file.
2. For Markdown, split by headings.
3. For source code, attempt logical blocks/functions/classes when parser support exists; fall back to line/character windows.
4. Apply configurable target and overlap.
5. Guarantee each chunk has file path and line range.

Chunk fingerprint = SHA-256 of normalized content + source path + start/end line + chunking version.

## 6. Hybrid retrieval
Use two candidate pools:
- dense top Kd using pgvector cosine distance
- lexical top Kl using PostgreSQL text ranking

Fuse with Reciprocal Rank Fusion:

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

where `k` is a configurable constant such as 60.

Then rerank the merged top N candidates.

## 7. Context assembly
For each final candidate:
- source path
- line range
- code/text
- language
- retrieval score

Deduplicate highly overlapping chunks. Enforce a context budget. Prefer diverse files/functions over ten nearly identical chunks.

## 8. Grounded answer contract
The LLM instruction must require:
- answer only from supplied context
- no unsupported paths/line numbers
- distinguish direct evidence from inference
- state that evidence is insufficient when appropriate
- return citation IDs corresponding only to supplied context

After generation, validate citation IDs and discard invalid references rather than inventing them.

## 9. Query response shape
```json
{
  "answer": "...",
  "citations": [
    {
      "file_path": "src/auth/service.py",
      "start_line": 24,
      "end_line": 47,
      "snippet": "...",
      "score": 0.91
    }
  ],
  "retrieval": {
    "dense_candidates": 8,
    "lexical_candidates": 8,
    "fused_candidates": 12,
    "reranked_candidates": 6,
    "latency_ms": 132
  }
}
```

## 10. Failure handling
- GitHub unavailable: show retryable upstream error.
- Rate-limited: respect retry headers/backoff.
- Repository too large: fail before expensive embedding if predicted limits are exceeded.
- Provider key missing: show a configuration error only for features requiring the provider.
- LLM timeout: return retrieval results and a useful error state rather than blank UI.
- Database unavailable: readiness should fail; liveness may remain healthy.

## 11. Security boundaries
- Browser never receives server-side API keys.
- GitHub token is server-side only.
- All input is validated.
- URLs are normalized and restricted to GitHub repository URLs.
- No arbitrary server-side URL fetching.
- Rate-limit query endpoints.
- Escape/render source code safely.
- Avoid executing repository code.
