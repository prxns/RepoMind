"""Source-level retrieval metrics with deterministic tie handling."""

import math


def score(retrieved: list[str], relevant: set[str], k: int) -> dict[str, float]:
    if not relevant:
        raise ValueError("Retrieval metrics require at least one relevant source.")
    top = retrieved[:k]
    hits = [1 if path in relevant else 0 for path in top]
    recall = len(set(top) & relevant) / len(relevant)
    precision = sum(hits) / k
    first = next((rank for rank, hit in enumerate(hits, 1) if hit), None)
    mrr = 1 / first if first else 0.0
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(hits, 1))
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return {"recall_at_k": recall, "precision_at_k": precision, "mrr_at_k": mrr,
            "ndcg_at_k": dcg / ideal if ideal else 0.0}
