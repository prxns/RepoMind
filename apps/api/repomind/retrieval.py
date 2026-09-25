"""Independent vector, lexical, fusion, reranking, and context stages."""

import time
import uuid
import re
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


GATE_STOPWORDS = {
    "a", "an", "and", "are", "current", "does", "for", "how", "in", "is", "it",
    "of", "on", "the", "this", "to", "what", "where", "which", "who", "with",
}


def _gate_terms(value: str) -> set[str]:
    return {
        term for term in re.findall(r"[a-z0-9]+", value.lower())
        if term not in GATE_STOPWORDS and len(term) > 1
    }


def _coverage(terms: set[str], value: str) -> tuple[int, float]:
    if not terms:
        return 0, 0.0
    present = _gate_terms(value)
    matched = len(terms & present)
    return matched, matched / len(terms)


def evidence_sufficiency(question: str, evidence: list[Evidence], dense: list[Candidate],
                         lexical: list[Candidate], fused: list[Candidate],
                         settings: Settings) -> dict:
    """Combine independent retrieval signals; no single score can pass the gate alone."""
    terms = _gate_terms(question)
    combined = "\n".join(f"{item.file_path}\n{item.content}" for item in evidence)
    matched_terms, lexical_coverage = _coverage(terms, combined)
    top_dense = max((item.score for item in dense), default=-1.0)
    dense_ids = {item.chunk.id for item in dense[:5]}
    lexical_ids = {item.chunk.id for item in lexical[:5]}
    agreement_denominator = max(1, min(len(dense_ids), len(lexical_ids)))
    rank_agreement = len(dense_ids & lexical_ids) / agreement_denominator
    top_evidence = evidence[0] if evidence else None
    _, reranker_overlap = _coverage(
        terms,
        f"{top_evidence.file_path}\n{top_evidence.content}" if top_evidence else "",
    )
    positive_fused = [max(item.score, 0.0) for item in fused[:5]]
    fused_total = sum(positive_fused)
    concentration = positive_fused[0] / fused_total if positive_fused and fused_total else 0.0
    dense_strength = max(0.0, min(1.0, (top_dense + 1.0) / 2.0))
    score = (
        lexical_coverage * 0.35
        + dense_strength * 0.25
        + rank_agreement * 0.20
        + reranker_overlap * 0.15
        + concentration * 0.05
    )
    signals = {
        "lexical_coverage": lexical_coverage >= settings.evidence_gate_min_lexical_coverage,
        "dense_similarity": top_dense >= settings.evidence_gate_min_dense_similarity,
        "rank_agreement": rank_agreement >= settings.evidence_gate_min_rank_agreement,
        "reranker_overlap": reranker_overlap >= settings.evidence_gate_min_reranker_overlap,
    }
    positive_count = sum(signals.values())
    enough_terms = matched_terms >= settings.evidence_gate_min_query_terms
    sufficient = bool(
        evidence
        and terms
        and enough_terms
        and positive_count >= settings.evidence_gate_min_signals
        and score >= settings.evidence_gate_min_score
    )
    reason = "sufficient" if sufficient else (
        "no_query_term_match" if not enough_terms else "weak_retrieval_signals"
    )
    return {
        "sufficient": sufficient,
        "reason": reason,
        "score": round(score, 4),
        "matched_query_terms": matched_terms,
        "query_term_count": len(terms),
        "positive_signal_count": positive_count,
        "signals": {
            "lexical_coverage": round(lexical_coverage, 4),
            "top_dense_similarity": round(top_dense, 4),
            "rank_agreement": round(rank_agreement, 4),
            "reranker_overlap": round(reranker_overlap, 4),
            "candidate_concentration": round(concentration, 4),
        },
    }


def retrieve(db: Session, snapshot: Snapshot, question: str, top_k: int,
             embeddings: EmbeddingProvider, settings: Settings,
             gate_question: str | None = None) -> tuple[list[Evidence], dict]:
    start = time.perf_counter()
    vector = embeddings.embed_query(question)
    if len(vector) != settings.embedding_dim:
        raise RuntimeError("Embedding provider returned the wrong vector dimension.")
    dense = vector_search(db, snapshot.id, vector, top_k * 3)
    lexical = lexical_search(db, snapshot.id, question, top_k * 3)
    fused = reciprocal_rank_fusion([dense, lexical])
    ordered = reranker_provider(settings).rank(question, fused[:top_k * 4])
    evidence = pack_context(ordered, settings.max_context_chars, top_k)
    gate = evidence_sufficiency(gate_question or question, evidence, dense, lexical, fused, settings)
    return evidence, {
        "dense_candidates": len(dense), "lexical_candidates": len(lexical),
        "fused_candidates": len(fused), "reranked_candidates": len(ordered),
        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        "evidence_gate": gate,
    }
