# Retrieval evaluation

`dataset.jsonl` contains 16 source-level questions about the public `prxns/RepoMind` repository. One case tests insufficient evidence; the other 15 have source labels. The benchmark requires that repository to have been indexed by a running RepoMind instance. Re-index after source changes so labels and indexed content match.

From the repository root, with the API package installed and the database running:

```bash
PYTHONPATH=apps/api python evals/run.py --k 5
```

The runner compares lexical, vector, reciprocal-rank hybrid, and hybrid plus token-overlap reranking. It writes measured JSON and Markdown to `evals/results/`, which is ignored by Git. Recall, precision, MRR, and nDCG are computed at the source-path level. Negative cases are excluded from retrieval metrics because no relevant source exists. Answer quality and citation validity are tested separately in the API/provider tests; this runner does not claim to measure model groundedness.
