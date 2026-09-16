"""Independent vector, lexical, fusion, reranking, and context stages."""

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from repomind.config import Settings
from repomind.models import Chunk, Snapshot, SourceFile
from repomind.providers import EmbeddingProvider, Evidence, TokenOverlapReranker, reranker_provider


@dataclass(frozen=True)
class Candidate:
    chunk: Chunk
    source: SourceFile
    score: float


def vector_search(db: Session, snapshot_id: uuid.UUID, vector: list[float], limit: int) -> list[Candidate]:
    distance = Chunk.embedding.cosine_distance(vector)
    rows = db.execute(
        select(Chunk, SourceFile, distance.label("distance"))
        .join(SourceFile, Chunk.source_file_id == SourceFile.id)
        .where(SourceFile.snapshot_id == snapshot_id)
        .order_by(distance).limit(limit)
    ).all()
    return [Candidate(chunk, source, 1 - float(score)) for chunk, source, score in rows]


def lexical_search(db: Session, snapshot_id: uuid.UUID, question: str, limit: int) -> list[Candidate]:
    query = func.plainto_tsquery("english", question)
    document = func.to_tsvector("english", Chunk.content)
    rank = func.ts_rank_cd(document, query)
    rows = db.execute(
        select(Chunk, SourceFile, rank.label("rank"))
        .join(SourceFile, Chunk.source_file_id == SourceFile.id)
        .where(SourceFile.snapshot_id == snapshot_id, document.op("@@")(query))
        .order_by(rank.desc()).limit(limit)
    ).all()
    return [Candidate(chunk, source, float(score)) for chunk, source, score in rows]


def reciprocal_rank_fusion(pools: list[list[Candidate]], k: int = 60) -> list[Candidate]:
    fused: dict[uuid.UUID, Candidate] = {}
    scores: dict[uuid.UUID, float] = {}
    for pool in pools:
        for rank, item in enumerate(pool, 1):
            fused[item.chunk.id] = item
            scores[item.chunk.id] = scores.get(item.chunk.id, 0) + 1 / (k + rank)
    return [Candidate(fused[key].chunk, fused[key].source, score)
            for key, score in sorted(scores.items(), key=lambda pair: (-pair[1], str(pair[0])))]


def rerank(question: str, candidates: list[Candidate]) -> list[Candidate]:
    return TokenOverlapReranker().rank(question, candidates)


def pack_context(candidates: list[Candidate], max_chars: int, limit: int) -> list[Evidence]:
    evidence: list[Evidence] = []
    budget = max_chars
    for item in candidates:
        if len(evidence) >= limit or budget <= 0:
            break
        if any(known.source_id == str(item.source.id)
               and item.chunk.start_line <= known.end_line
               and item.chunk.end_line >= known.start_line for known in evidence):
            continue
        content = item.chunk.content[:budget]
        if not content.strip():
            continue
        evidence.append(Evidence(f"S{len(evidence) + 1}", str(item.source.id), item.source.path,
                                 item.chunk.start_line, item.chunk.end_line, content, item.score))
        budget -= len(content)
    return evidence


def retrieve(db: Session, snapshot: Snapshot, question: str, top_k: int,
             embeddings: EmbeddingProvider, settings: Settings) -> tuple[list[Evidence], dict]:
    start = time.perf_counter()
    vector = embeddings.embed_query(question)
    if len(vector) != settings.embedding_dim:
        raise RuntimeError("Embedding provider returned the wrong vector dimension.")
    dense = vector_search(db, snapshot.id, vector, top_k * 3)
    lexical = lexical_search(db, snapshot.id, question, top_k * 3)
    fused = reciprocal_rank_fusion([dense, lexical])
    ordered = reranker_provider(settings).rank(question, fused[:top_k * 4])
    evidence = pack_context(ordered, settings.max_context_chars, top_k)
    return evidence, {
        "dense_candidates": len(dense), "lexical_candidates": len(lexical),
        "fused_candidates": len(fused), "reranked_candidates": len(ordered),
        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
    }
