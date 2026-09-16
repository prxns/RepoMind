# RepoMind — Data Model

Use PostgreSQL + pgvector. Use UUID primary keys unless a natural key is clearly preferable.

## Tables

### repositories
- id UUID PK
- owner VARCHAR
- name VARCHAR
- full_name VARCHAR UNIQUE
- default_branch VARCHAR
- html_url TEXT
- description TEXT NULL
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ

### repository_snapshots
- id UUID PK
- repository_id UUID FK
- ref VARCHAR
- commit_sha VARCHAR NULL
- snapshot_fingerprint VARCHAR
- status VARCHAR
- files_seen INT
- files_indexed INT
- chunks_created INT
- started_at TIMESTAMPTZ NULL
- completed_at TIMESTAMPTZ NULL
- error_code VARCHAR NULL
- error_message TEXT NULL

Unique index: `(repository_id, snapshot_fingerprint)`.

### source_files
- id UUID PK
- snapshot_id UUID FK
- path TEXT
- language VARCHAR NULL
- github_sha VARCHAR NULL
- byte_size INT
- line_count INT
- content_hash VARCHAR
- content TEXT (or compressed representation if implementation justifies it)
- created_at TIMESTAMPTZ

Unique index: `(snapshot_id, path, content_hash)`.

### chunks
- id UUID PK
- source_file_id UUID FK
- chunk_index INT
- start_line INT
- end_line INT
- content TEXT
- content_hash VARCHAR
- metadata JSONB
- embedding VECTOR(D) where D matches the selected embedding implementation
- tsv TSVECTOR GENERATED/STORED where supported, or a maintained indexed search column

Indexes:
- HNSW cosine index on embedding.
- GIN index on lexical-search representation.
- B-tree on snapshot_id and source_file_id.

### ingestion_jobs
- id UUID PK
- repository_id UUID FK
- snapshot_id UUID NULL FK
- status VARCHAR
- progress_json JSONB
- error_code VARCHAR NULL
- error_message TEXT NULL
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ

### sessions
- id UUID PK
- repository_id UUID FK
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ

### messages
- id UUID PK
- session_id UUID FK
- role VARCHAR
- content TEXT
- citations JSONB
- retrieval_metadata JSONB
- created_at TIMESTAMPTZ

### evaluation_runs (optional)
- id UUID PK
- dataset_version VARCHAR
- config JSONB
- metrics JSONB
- created_at TIMESTAMPTZ

## Data integrity
- Foreign keys must be enforced.
- Status values should be constrained via enums/check constraints.
- Deleting a repository should cascade to snapshots, files, chunks, jobs, sessions, and messages where appropriate.
- Transactions should wrap snapshot/index state transitions.

## Vector dimension
Do not hardcode a model-specific dimension in application code. Store it in configuration and validate at startup. Migration generation should use the selected production dimension.
