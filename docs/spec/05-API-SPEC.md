# RepoMind — API Specification

Base prefix: `/api/v1`

## POST `/repositories/ingest`
Start ingestion.

Request:
```json
{
  "url": "https://github.com/owner/repo",
  "ref": null
}
```

Response `202`:
```json
{
  "job_id": "uuid",
  "repository_id": "uuid",
  "status": "PENDING"
}
```

## GET `/repositories/{repository_id}`
Return repository metadata and latest ingestion status.

## GET `/ingestion/{job_id}`
Return status/counters:
```json
{
  "job_id": "uuid",
  "status": "EMBEDDING",
  "files_seen": 420,
  "files_indexed": 315,
  "chunks_created": 4821,
  "started_at": "...",
  "updated_at": "...",
  "error": null
}
```

## POST `/repositories/{repository_id}/query`
Request:
```json
{
  "question": "Where is authentication implemented?",
  "session_id": null,
  "top_k": 8,
  "debug": false
}
```

Response `200`: see SDS response contract.

## GET `/repositories/{repository_id}/sources/{source_id}`
Return source metadata and a bounded snippet for citation inspection.

## GET `/sessions/{session_id}`
Return recent questions/answers for the current repository session.

## GET `/health/live`
Returns basic process health.

## GET `/health/ready`
Checks database and required configuration/provider reachability as appropriate.

## Error format
```json
{
  "error": {
    "code": "REPOSITORY_NOT_FOUND",
    "message": "Repository could not be resolved.",
    "retryable": false,
    "request_id": "uuid"
  }
}
```

## API rules
- Use Pydantic response/request models.
- Add OpenAPI descriptions/examples.
- Validate all IDs and URL inputs.
- Add request IDs to responses/log context.
- Do not leak stack traces in production responses.
- Keep endpoints narrow; avoid generic `/chat` or `/do-everything` APIs.
