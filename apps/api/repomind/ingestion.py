"""Idempotent, database-backed ingestion jobs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from repomind.config import Settings
from repomind.db import SessionLocal
from repomind.github import GithubClient, GithubError
from repomind.models import Chunk, IngestionJob, Repository, Snapshot, SourceFile
from repomind.providers import EmbeddingProvider, LocalEmbedding
from repomind.source import chunk_text, fingerprint, normalized_text, supported_file


def _status(db: Session, job: IngestionJob, snapshot: Snapshot | None, status: str) -> None:
    job.status = status
    job.updated_at = datetime.now(timezone.utc)
    if snapshot:
        snapshot.status = status
    db.commit()


def delete_repository(db: Session, repository_id: uuid.UUID) -> bool:
    repository = db.get(Repository, repository_id)
    if repository is None:
        return False
    db.delete(repository)
    db.commit()
    return True


def _copy_unchanged(db: Session, repository_id: uuid.UUID, snapshot: Snapshot,
                    path: str, sha: str) -> SourceFile | None:
    previous = db.execute(
        select(SourceFile)
        .join(Snapshot, SourceFile.snapshot_id == Snapshot.id)
        .where(Snapshot.repository_id == repository_id, Snapshot.status == "COMPLETED",
               SourceFile.path == path, SourceFile.github_sha == sha)
        .order_by(Snapshot.completed_at.desc()).limit(1)
    ).scalar_one_or_none()
    if previous is None:
        return None
    copied = SourceFile(snapshot_id=snapshot.id, path=previous.path, language=previous.language,
                        github_sha=sha, byte_size=previous.byte_size,
                        line_count=previous.line_count, content_hash=previous.content_hash,
                        content=previous.content)
    db.add(copied)
    db.flush()
    for old in db.scalars(select(Chunk).where(Chunk.source_file_id == previous.id)):
        db.add(Chunk(source_file_id=copied.id, chunk_index=old.chunk_index,
                     start_line=old.start_line, end_line=old.end_line,
                     content=old.content, content_hash=old.content_hash,
                     embedding=old.embedding))
    return copied


def run_job(job_id: uuid.UUID, settings: Settings, github: GithubClient | None = None,
            embeddings: EmbeddingProvider | None = None,
            session_factory=SessionLocal) -> None:
    github = github or GithubClient(settings)
    embeddings = embeddings or LocalEmbedding(settings.embedding_model)
    with session_factory() as db:
        job = db.get(IngestionJob, job_id)
        if job is None:
            return
        repo = db.get(Repository, job.repository_id)
        if repo is None:
            return
        snapshot = None
        try:
            _status(db, job, None, "FETCHING")
            ref = job.progress_json["ref"]
            commit_sha, tree = github.snapshot_tree(repo.owner, repo.name, ref)
            eligible = [(item, supported_file(item.path, item.size, settings.max_file_bytes))
                        for item in tree]
            eligible = [(item, language) for item, language in eligible if language]
            if len(eligible) > settings.max_files or sum(item.size for item, _ in eligible) > settings.max_total_bytes:
                raise GithubError("REPOSITORY_TOO_LARGE", "Repository exceeds configured indexing limits.")
            identity = fingerprint(repo.full_name, ref, commit_sha, "chunk-v1", settings.embedding_model)
            snapshot = db.execute(select(Snapshot).where(
                Snapshot.repository_id == repo.id,
                Snapshot.snapshot_fingerprint == identity)).scalar_one_or_none()
            if snapshot and snapshot.status == "COMPLETED":
                job.snapshot_id = snapshot.id
                job.progress_json = {"ref": ref, "files_seen": snapshot.files_seen,
                                     "files_indexed": snapshot.files_indexed,
                                     "chunks_created": snapshot.chunks_created}
                _status(db, job, snapshot, "COMPLETED")
                return
            if snapshot is None:
                snapshot = Snapshot(repository_id=repo.id, ref=ref, commit_sha=commit_sha,
                                    snapshot_fingerprint=identity, started_at=datetime.now(timezone.utc))
                db.add(snapshot)
                db.flush()
            else:
                for old_file in db.scalars(select(SourceFile).where(SourceFile.snapshot_id == snapshot.id)):
                    db.delete(old_file)
                db.flush()
                snapshot.started_at = datetime.now(timezone.utc)
            job.snapshot_id = snapshot.id
            snapshot.files_seen = len(tree)
            snapshot.files_indexed = 0
            snapshot.chunks_created = 0
            _status(db, job, snapshot, "PARSING")
            for item, language in eligible:
                copied = _copy_unchanged(db, repo.id, snapshot, item.path, item.sha)
                if copied:
                    count = db.query(Chunk).filter(Chunk.source_file_id == copied.id).count()
                    snapshot.files_indexed += 1
                    snapshot.chunks_created += count
                else:
                    raw = github.blob(repo.owner, repo.name, item.sha)
                    if len(raw) > settings.max_file_bytes:
                        continue
                    content = normalized_text(raw)
                    if content is None or not content.strip():
                        continue
                    parts = chunk_text(item.path, content, language,
                                       settings.chunk_target_lines, settings.chunk_overlap_lines)
                    if snapshot.chunks_created + len(parts) > settings.max_chunks:
                        raise GithubError("TOO_MANY_CHUNKS", "Repository exceeds the chunk limit.")
                    source = SourceFile(snapshot_id=snapshot.id, path=item.path, language=language,
                                        github_sha=item.sha, byte_size=len(raw),
                                        line_count=len(content.splitlines()),
                                        content_hash=fingerprint(content), content=content)
                    db.add(source)
                    db.flush()
                    _status(db, job, snapshot, "EMBEDDING")
                    vectors = embeddings.embed_documents([part.content for part in parts])
                    if len(vectors) != len(parts) or any(len(vector) != settings.embedding_dim for vector in vectors):
                        raise RuntimeError("Embedding provider returned the wrong vector dimension.")
                    for part, vector in zip(parts, vectors):
                        db.add(Chunk(source_file_id=source.id, chunk_index=part.index,
                                     start_line=part.start_line, end_line=part.end_line,
                                     content=part.content, content_hash=part.content_hash,
                                     embedding=vector))
                    snapshot.files_indexed += 1
                    snapshot.chunks_created += len(parts)
                job.progress_json = {"ref": ref, "files_seen": len(tree),
                                     "files_indexed": snapshot.files_indexed,
                                     "chunks_created": snapshot.chunks_created}
                _status(db, job, snapshot, "INDEXING")
            snapshot.completed_at = datetime.now(timezone.utc)
            _status(db, job, snapshot, "COMPLETED")
        except Exception as exc:
            db.rollback()
            job = db.get(IngestionJob, job_id)
            snapshot = db.get(Snapshot, job.snapshot_id) if job and job.snapshot_id else None
            if job:
                code = exc.code if isinstance(exc, GithubError) else "INGESTION_FAILED"
                message = str(exc) if isinstance(exc, GithubError) else "Ingestion failed. Check server logs."
                job.error_code, job.error_message = code, message
                if snapshot:
                    snapshot.error_code, snapshot.error_message = code, message
                _status(db, job, snapshot, "FAILED")
            raise
