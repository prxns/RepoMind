import uuid
from types import SimpleNamespace

from repomind.config import Settings
from repomind.providers import Evidence, GeneratedAnswer, valid_citations
from repomind.retrieval import (
    Candidate,
    evidence_sufficiency,
    pack_context,
    reciprocal_rank_fusion,
    rerank,
)


def candidate(name: str, text: str, score: float = 0.0) -> Candidate:
    chunk = SimpleNamespace(id=uuid.uuid5(uuid.NAMESPACE_DNS, name), content=text,
                            start_line=1, end_line=4)
    source = SimpleNamespace(id=uuid.uuid5(uuid.NAMESPACE_DNS, name + "source"), path=name)
    return Candidate(chunk, source, score)


def test_rrf_rewards_results_in_both_pools():
    a, b, c = candidate("a.py", "auth"), candidate("b.py", "db"), candidate("c.py", "user")
    results = reciprocal_rank_fusion([[a, b], [c, a]])
    assert results[0].chunk.id == a.chunk.id
    assert len(results) == 3


def test_rerank_and_context_have_real_source_ranges():
    a, b = candidate("auth.py", "login authentication user"), candidate("db.py", "database")
    ordered = rerank("authentication", [b, a])
    assert ordered[0].source.path == "auth.py"
    context = pack_context(ordered, 100, 2)
    assert context[0].citation_id == "S1"
    assert context[0].start_line == 1


def test_invalid_citation_markers_are_removed():
    evidence = [Evidence("S1", "id", "auth.py", 1, 4, "login", 0.9)]
    result = valid_citations(GeneratedAnswer("Login is here [S1]. Ignore [S99].", ["S1", "S99"]), evidence)
    assert result.citation_ids == ["S1"]
    assert "[S99]" not in result.answer


def test_evidence_gate_accepts_agreeing_relevant_signals():
    item = candidate(
        "retrieval.py",
        "def reciprocal_rank_fusion(dense, lexical): return fused_results",
        0.82,
    )
    fused = reciprocal_rank_fusion([[item], [item]])
    selected = pack_context(fused, 1000, 3)

    result = evidence_sufficiency(
        "How are dense and lexical results fused?",
        selected,
        [item],
        [item],
        fused,
        Settings(_env_file=None),
    )

    assert result["sufficient"] is True
    assert result["positive_signal_count"] >= 2
    assert result["matched_query_terms"] >= 2


def test_evidence_gate_rejects_unrelated_dense_neighbor():
    item = candidate(
        "retrieval.py",
        "def reciprocal_rank_fusion(dense, lexical): return fused_results",
        0.91,
    )
    selected = pack_context([item], 1000, 3)

    result = evidence_sufficiency(
        "Who is the current CEO of Microsoft?",
        selected,
        [item],
        [],
        [item],
        Settings(_env_file=None),
    )

    assert result["sufficient"] is False
    assert result["reason"] == "no_query_term_match"
    assert result["matched_query_terms"] == 0
