"""Versioned HTTP API for repository ingestion and grounded queries."""

import asyncio
import uuid
from datetime import datetime, timezone
from threading import BoundedSemaphore
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from repomind.config import get_settings
from repomind.db import SessionLocal, check_ready, get_db
from repomind.github import GithubClient, GithubError
from repomind.ingestion import run_job
from repomind.limits import PostRateLimiter
from repomind.models import IngestionJob, Message, QuerySession, Repository, Snapshot, SourceFile
from repomind.providers import LocalEmbedding, answer_provider, valid_citations
from repomind.retrieval import retrieve
from repomind.source import parse_repo_url, validate_ref


settings = get_settings()
app = FastAPI(title="RepoMind API", version="0.1.0", description="Repository-aware search and answers")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
                   allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Request-ID"])
rate_limiter = PostRateLimiter(settings.rate_limit_per_minute, settings.global_rate_limit_per_minute)
query_slots = BoundedSemaphore(settings.max_concurrent_queries)
embeddings = LocalEmbedding(settings.embedding_model)
ACTIVE_JOBS = ("PENDING", "FETCHING", "PARSING", "EMBEDDING", "INDEXING")


@app.on_event("startup")
async def restart_interrupted_jobs() -> None:
    try:
        with SessionLocal() as db:
            jobs = db.scalars(select(IngestionJob).where(IngestionJob.status.in_(ACTIVE_JOBS))).all()
            ids = [job.id for job in jobs]
    except SQLAlchemyError:
        return
    for job_id in ids:
        asyncio.create_task(asyncio.to_thread(run_job, job_id, settings))


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, retryable: bool = False):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


class IngestRequest(BaseModel):
    url: str = Field(min_length=20, max_length=500)
    ref: str | None = Field(default=None, max_length=255)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        parse_repo_url(value)
        return value

    @field_validator("ref")
    @classmethod
    def valid_ref(cls, value: str | None) -> str | None:
        return validate_ref(value) if value else None


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    session_id: uuid.UUID | None = None
    top_k: int = Field(default=8, ge=3, le=12)
    debug: bool = False

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank.")
        return value.strip()


def _error(request: Request, status: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "retryable": retryable,
        "request_id": getattr(request.state, "request_id", ""),
    }})


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    if request.method == "POST":
        # The socket peer is stable across paths and malformed Host values. A trusted
        # reverse proxy must supply its own admission control for multiple API replicas.
        client = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client):
            response = _error(request, 429, "RATE_LIMITED", "Too many requests. Try again shortly.", True)
            response.headers["X-Request-ID"] = request.state.request_id
            return response
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(ApiError)
async def api_error(request: Request, exc: ApiError):
    return _error(request, exc.status_code, exc.code, exc.message, exc.retryable)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return _error(request, 422, "INVALID_INPUT", "Check the request fields and try again.")


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    return _error(request, 503, "DATABASE_UNAVAILABLE", "Database is unavailable.", True)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    return _error(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")


@app.get("/api/v1/health/live", tags=["health"])
def live():
    return {"status": "ok"}


@app.get("/api/v1/health/ready", tags=["health"])
def ready():
    try:
        check_ready()
    except Exception as exc:
        raise ApiError(503, "NOT_READY", "Database or embedding schema is not ready.", True) from exc
    return {"status": "ready"}


@app.post("/api/v1/repositories/ingest", status_code=202, tags=["repositories"])
def ingest(payload: IngestRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    owner, name = parse_repo_url(payload.url)
    try:
        remote = GithubClient(settings).repository(owner, name)
    except GithubError as exc:
        status = 429 if exc.code == "GITHUB_RATE_LIMITED" else 404 if exc.code == "REPOSITORY_NOT_FOUND" else 502
        raise ApiError(status, exc.code, str(exc), exc.retryable) from exc
    full_name = remote["full_name"]
    # Serialize admission across API processes before counting or inserting jobs.
    db.execute(text("SELECT pg_advisory_xact_lock(84238012)"))
    repo = db.scalar(select(Repository).where(Repository.full_name == full_name))
    if repo is not None:
        existing = db.scalar(select(IngestionJob).where(
            IngestionJob.repository_id == repo.id, IngestionJob.status.in_(ACTIVE_JOBS))
            .order_by(IngestionJob.created_at.desc()).limit(1))
        if existing:
            db.rollback()
            return {"job_id": existing.id, "repository_id": repo.id, "status": existing.status}
    active = db.scalar(select(func.count(IngestionJob.id)).where(IngestionJob.status.in_(ACTIVE_JOBS)))
    if active is not None and active >= settings.max_active_ingestions:
        raise ApiError(429, "INGESTION_CAPACITY", "Indexing capacity is full. Try again later.", True)
    if repo is None:
        repo = Repository(owner=owner, name=name, full_name=full_name,
                          default_branch=remote["default_branch"],
                          html_url=remote["html_url"], description=remote.get("description"))
        db.add(repo)
        db.flush()
    else:
        repo.default_branch = remote["default_branch"]
        repo.description = remote.get("description")
    ref = payload.ref or repo.default_branch
    job = IngestionJob(repository_id=repo.id, status="PENDING", progress_json={
        "ref": ref, "files_seen": 0, "files_indexed": 0, "chunks_created": 0,
    })
    db.add(job)
    db.commit()
    background.add_task(run_job, job.id, settings)
    return {"job_id": job.id, "repository_id": repo.id, "status": job.status}


@app.get("/api/v1/repositories/{repository_id}", tags=["repositories"])
def repository(repository_id: uuid.UUID, db: Session = Depends(get_db)):
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise ApiError(404, "REPOSITORY_NOT_FOUND", "Repository was not found.")
    latest = db.scalar(select(IngestionJob).where(IngestionJob.repository_id == repo.id)
                       .order_by(IngestionJob.created_at.desc()).limit(1))
    return {"id": repo.id, "full_name": repo.full_name, "default_branch": repo.default_branch,
            "description": repo.description, "html_url": repo.html_url,
            "latest_ingestion": latest.status if latest else None,
            "latest_ref": latest.progress_json.get("ref") if latest else None}


@app.get("/api/v1/ingestion/{job_id}", tags=["ingestion"])
def ingestion(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise ApiError(404, "JOB_NOT_FOUND", "Ingestion job was not found.")
    return {"job_id": job.id, "repository_id": job.repository_id,
            "status": job.status, **job.progress_json,
            "started_at": job.created_at, "updated_at": job.updated_at,
            "error": {"code": job.error_code, "message": job.error_message} if job.error_code else None}


@app.post("/api/v1/repositories/{repository_id}/query", tags=["query"])
def query(repository_id: uuid.UUID, payload: QueryRequest, db: Session = Depends(get_db)):
    if not query_slots.acquire(blocking=False):
        raise ApiError(429, "QUERY_CAPACITY", "Question capacity is full. Try again later.", True)
    try:
        return _query(repository_id, payload, db)
    finally:
        query_slots.release()


def _query(repository_id: uuid.UUID, payload: QueryRequest, db: Session):
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise ApiError(404, "REPOSITORY_NOT_FOUND", "Repository was not found.")
    snapshot = db.scalar(select(Snapshot).where(Snapshot.repository_id == repo.id,
                                                Snapshot.status == "COMPLETED")
                         .order_by(Snapshot.completed_at.desc()).limit(1))
    if snapshot is None:
        raise ApiError(409, "NOT_INDEXED", "Index this repository before asking questions.")
    if payload.session_id:
        session = db.get(QuerySession, payload.session_id)
        if session is None or session.repository_id != repository_id:
            raise ApiError(404, "SESSION_NOT_FOUND", "Session was not found for this repository.")
        previous = db.scalar(select(Message).where(Message.session_id == session.id,
                                                   Message.role == "user")
                             .order_by(Message.created_at.desc()).limit(1))
    else:
        session = QuerySession(repository_id=repo.id)
        db.add(session)
        db.flush()
        previous = None
    contextual_question = (f"Previous question: {previous.content[:1000]}\nFollow-up: {payload.question}"
                           if previous else payload.question)
    try:
        evidence, metadata = retrieve(db, snapshot, contextual_question, payload.top_k, embeddings, settings)
        generated = valid_citations(answer_provider(settings).generate(contextual_question, evidence), evidence)
    except ValueError as exc:
        raise ApiError(503, "PROVIDER_NOT_CONFIGURED", str(exc)) from exc
    except Exception as exc:
        raise ApiError(502, "GENERATION_FAILED", "Retrieval or generation failed. Try again.", True) from exc
    citations = []
    for item in evidence:
        if item.citation_id not in generated.citation_ids:
            continue
        path = quote(item.file_path, safe="/")
        citations.append({"id": item.citation_id, "source_id": item.source_id,
                          "file_path": item.file_path, "start_line": item.start_line,
                          "end_line": item.end_line, "snippet": item.content[:800],
                          "score": round(item.score, 4),
                          "url": f"{repo.html_url}/blob/{snapshot.commit_sha}/{path}#L{item.start_line}-L{item.end_line}"})
    metadata["sources"] = [{"path": item.file_path, "start_line": item.start_line,
                            "end_line": item.end_line, "score": round(item.score, 4)}
                           for item in evidence] if payload.debug else []
    db.add(Message(session_id=session.id, role="user", content=payload.question,
                   citations=[], retrieval_metadata={}))
    db.add(Message(session_id=session.id, role="assistant", content=generated.answer,
                   citations=citations, retrieval_metadata=metadata))
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"answer": generated.answer, "citations": citations,
            "retrieval": metadata, "session_id": session.id}


@app.get("/api/v1/repositories/{repository_id}/sources/{source_id}", tags=["sources"])
def source(repository_id: uuid.UUID, source_id: uuid.UUID, start_line: int = Query(default=1, ge=1),
           end_line: int = Query(default=100, ge=1), db: Session = Depends(get_db)):
    if end_line < start_line or end_line - start_line > 199:
        raise ApiError(422, "INVALID_RANGE", "Source range must be at most 200 lines.")
    source_file = db.scalar(select(SourceFile).join(Snapshot, SourceFile.snapshot_id == Snapshot.id)
                            .where(SourceFile.id == source_id, Snapshot.repository_id == repository_id))
    if source_file is None:
        raise ApiError(404, "SOURCE_NOT_FOUND", "Source was not found.")
    lines = source_file.content.splitlines()
    return {"id": source_file.id, "file_path": source_file.path,
            "language": source_file.language, "start_line": start_line,
            "end_line": min(end_line, len(lines)), "content": "\n".join(lines[start_line - 1:end_line])}


@app.get("/api/v1/sessions/{session_id}", tags=["sessions"])
def session_history(session_id: uuid.UUID, db: Session = Depends(get_db)):
    session = db.get(QuerySession, session_id)
    if session is None:
        raise ApiError(404, "SESSION_NOT_FOUND", "Session was not found.")
    messages = db.scalars(select(Message).where(Message.session_id == session_id)
                          .order_by(Message.created_at.desc()).limit(40)).all()
    return {"session_id": session.id, "repository_id": session.repository_id,
            "messages": [{"role": item.role, "content": item.content,
                          "citations": item.citations,
                          "retrieval": item.retrieval_metadata,
                          "created_at": item.created_at}
                         for item in reversed(messages)]}
