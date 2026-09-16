# RepoMind — RAG Evaluation Plan

A serious RAG project must measure retrieval separately from answer generation.

## 1. Benchmark dataset
Check in `evals/dataset.jsonl` with 15–30 questions over 2–3 small public repositories.

Each case should contain:
```json
{
  "id": "auth-001",
  "repository": "owner/repo",
  "question": "Where is authentication implemented?",
  "relevant_sources": [
    {"path": "src/auth/service.py", "start_line": 10, "end_line": 60}
  ],
  "reference_answer": "Authentication is implemented in ..."
}
```

The dataset should cover:
- direct file lookup
- cross-file architecture questions
- symbol/function questions
- configuration questions
- testing questions
- negative/insufficient-evidence questions

## 2. Retrieval metrics
At minimum compute:
- Recall@K
- Precision@K
- MRR

Where practical also compute nDCG@K.

Ground truth is source-level relevance, not exact text match.

## 3. Answer metrics
For MVP use transparent, reproducible metrics:
- Citation validity rate: all returned citations reference real retrieved chunks.
- Citation coverage: fraction of substantive answer claims linked to evidence where evidence exists.
- Groundedness score: evaluator rubric comparing answer statements against supplied context.
- Abstention correctness on negative questions.

LLM-as-judge may be included as an optional experiment, but its use and prompt must be documented. Do not present it as objective truth.

## 4. Baseline comparison
Evaluation runner should support at least:
- lexical-only
- vector-only
- hybrid
- hybrid + reranker

This demonstrates why each stage exists.

## 5. Evaluation output
Produce JSON and human-readable Markdown:
```text
Dataset: v1
Questions: 24
Recall@5: ...
MRR@5: ...
Citation validity: ...
Abstention accuracy: ...
```

All metrics must be computed from real runs. No hardcoded claims.

## 6. Reproducibility
Pin dependency versions through lock files. Store embedding/reranker/model configuration with each run. Make seeds configurable where relevant.
