import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select

from repomind.api import ApiError, IngestRequest, ingest, settings as api_settings
from repomind.config import Settings
from repomind.db import SessionLocal
from repomind.github import TreeFile
from repomind.ingestion import run_job
from repomind.models import Chunk, IngestionJob, Repository, Snapshot, SourceFile
from repomind.retrieval import retrieve


class FakeGithub:
    def snapshot_tree(self, owner, name, ref):
        return "a" * 40, [TreeFile("src/auth.py", "b" * 40, 42)]

    def blob(self, owner, name, sha):
        return b"def login(user):\n    return check_password(user)\n"


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        vector = [0.0] * 384
        vector[0] = 1.0 if "login" in text else 0.1
        vector[1] = 0.1 if "login" in text else 1.0
        return vector


def test_concurrent_jobs_for_one_repository_do_not_overlap():
    class SlowGithub(FakeGithub):
        def __init__(self):
            self.active = 0
            self.peak = 0
            self.lock = Lock()

        def snapshot_tree(self, owner, name, ref):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.2)
            try:
                return super().snapshot_tree(owner, name, ref)
            finally:
                with self.lock:
                    self.active -= 1

    repository_id = None
    with SessionLocal() as db:
        name = f"concurrent-{uuid.uuid4().hex}"
        repo = Repository(owner="repomind-test", name=name,
                          full_name=f"repomind-test/{name}", default_branch="main",
                          html_url=f"https://github.com/repomind-test/{name}", description=None)
        db.add(repo)
        db.flush()
        repository_id = repo.id
        jobs = [IngestionJob(repository_id=repo.id, progress_json={"ref": "main"}) for _ in range(2)]
        db.add_all(jobs)
        db.commit()
        job_ids = [job.id for job in jobs]
    github = SlowGithub()
    barrier = Barrier(2)

    def work(job_id):
        barrier.wait()
        run_job(job_id, Settings(), github, FakeEmbeddings())

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(work, job_ids))
        with SessionLocal() as db:
            assert all(db.get(IngestionJob, job_id).status == "COMPLETED" for job_id in job_ids)
            assert len(db.scalars(select(Snapshot).where(
                Snapshot.repository_id == repository_id)).all()) == 1
            assert github.peak == 1
    finally:
        with SessionLocal() as db:
            repo = db.get(Repository, repository_id)
            if repo:
                db.delete(repo)
                db.commit()


def test_ingestion_admission_reuses_job_and_caps_queue(monkeypatch):
    class RepositoryClient:
        def __init__(self, settings):
            pass

        def repository(self, owner, name):
            return {"full_name": f"{owner}/{name}", "default_branch": "main",
                    "html_url": f"https://github.com/{owner}/{name}"}

    monkeypatch.setattr("repomind.api.GithubClient", RepositoryClient)
    monkeypatch.setattr(api_settings, "max_active_ingestions", 1)
    first_name = f"admission-{uuid.uuid4().hex}"
    second_name = f"admission-{uuid.uuid4().hex}"
    try:
        with SessionLocal() as db:
            first = ingest(IngestRequest(url=f"https://github.com/repomind-test/{first_name}"),
                           BackgroundTasks(), db)
            reused = ingest(IngestRequest(url=f"https://github.com/repomind-test/{first_name}"),
                            BackgroundTasks(), db)
            assert reused["job_id"] == first["job_id"]
            with pytest.raises(ApiError) as error:
                ingest(IngestRequest(url=f"https://github.com/repomind-test/{second_name}"),
                       BackgroundTasks(), db)
            assert error.value.code == "INGESTION_CAPACITY"
            db.rollback()
    finally:
        with SessionLocal() as db:
            repo = db.scalar(select(Repository).where(
                Repository.full_name == f"repomind-test/{first_name}"))
            if repo:
                db.delete(repo)
                db.commit()


def test_ingestion_capacity_is_atomic_across_requests(monkeypatch):
    class RepositoryClient:
        def __init__(self, settings):
            pass

        def repository(self, owner, name):
            return {"full_name": f"{owner}/{name}", "default_branch": "main",
                    "html_url": f"https://github.com/{owner}/{name}"}

    monkeypatch.setattr("repomind.api.GithubClient", RepositoryClient)
    monkeypatch.setattr(api_settings, "max_active_ingestions", 1)
    names = [f"capacity-{uuid.uuid4().hex}" for _ in range(2)]
    barrier = Barrier(2)

    def submit(name):
        with SessionLocal() as db:
            barrier.wait()
            try:
                return ingest(IngestRequest(url=f"https://github.com/repomind-test/{name}"),
                              BackgroundTasks(), db)["status"]
            except ApiError as error:
                db.rollback()
                return error.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(submit, names)) == ["INGESTION_CAPACITY", "PENDING"]
    finally:
        with SessionLocal() as db:
            for name in names:
                repo = db.scalar(select(Repository).where(
                    Repository.full_name == f"repomind-test/{name}"))
                if repo:
                    db.delete(repo)
            db.commit()


def test_ingestion_is_idempotent_and_retrievable():
    settings = Settings()
    full_name = f"repomind-test/{uuid.uuid4().hex}"
    with SessionLocal() as db:
        repository = Repository(owner="repomind-test", name=full_name.split("/")[1],
                                full_name=full_name, default_branch="main",
                                html_url=f"https://github.com/{full_name}", description=None)
        db.add(repository)
        db.flush()
        repository_id = repository.id
        job = IngestionJob(repository_id=repository_id, progress_json={"ref": "main"})
        db.add(job)
        db.commit()
        first_job_id = job.id
    try:
        run_job(first_job_id, settings, FakeGithub(), FakeEmbeddings())
        class NoReplayGithub(FakeGithub):
            def snapshot_tree(self, owner, name, ref):
                raise AssertionError("A completed job must not be restarted.")

        run_job(first_job_id, settings, NoReplayGithub(), FakeEmbeddings())
        with SessionLocal() as db:
            first = db.get(IngestionJob, first_job_id)
            assert first.status == "COMPLETED"
            snapshot = db.get(Snapshot, first.snapshot_id)
            assert snapshot.files_indexed == 1
            assert snapshot.chunks_created == 1
            evidence, metadata = retrieve(db, snapshot, "Where is login?", 3, FakeEmbeddings(), settings)
            assert evidence[0].file_path == "src/auth.py"
            assert evidence[0].start_line == 1
            assert metadata["dense_candidates"] == 1
            second = IngestionJob(repository_id=repository_id, progress_json={"ref": "main"})
            db.add(second)
            db.commit()
            second_id = second.id
        run_job(second_id, settings, FakeGithub(), FakeEmbeddings())
        with SessionLocal() as db:
            assert db.get(IngestionJob, second_id).status == "COMPLETED"
            assert len(db.scalars(select(Snapshot).where(Snapshot.repository_id == repository_id)).all()) == 1
            assert len(db.scalars(select(SourceFile).where(SourceFile.snapshot_id == snapshot.id)).all()) == 1
            assert len(db.scalars(select(Chunk).join(SourceFile).where(SourceFile.snapshot_id == snapshot.id)).all()) == 1
    finally:
        with SessionLocal() as db:
            repository = db.get(Repository, repository_id)
            if repository:
                db.delete(repository)
                db.commit()
