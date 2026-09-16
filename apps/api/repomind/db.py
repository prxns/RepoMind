from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from repomind.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def check_ready() -> None:
    with engine.connect() as connection:
        dimension = connection.execute(
            text("SELECT format_type(a.atttypid, a.atttypmod) "
                 "FROM pg_attribute a WHERE a.attrelid = 'chunks'::regclass "
                 "AND a.attname = 'embedding'")
        ).scalar_one()
        expected = f"vector({get_settings().embedding_dim})"
        if dimension != expected:
            raise RuntimeError(f"Embedding schema is {dimension}; expected {expected}")
