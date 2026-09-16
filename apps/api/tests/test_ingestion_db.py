import uuid

from sqlalchemy import select

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
