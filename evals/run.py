"""Run retrieval baselines against an indexed public RepoMind snapshot."""

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from repomind.config import get_settings
from repomind.db import SessionLocal
from repomind.models import Repository, Snapshot
from repomind.providers import LocalEmbedding
from repomind.retrieval import lexical_search, reciprocal_rank_fusion, rerank, vector_search

from metrics import score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("dataset.jsonl"))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "latest.json")
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    settings = get_settings()
    embeddings = LocalEmbedding(settings.embedding_model)
    methods = {name: [] for name in ("lexical", "vector", "hybrid", "hybrid_rerank")}
    with SessionLocal() as db:
        for case in cases:
            if not case["relevant_sources"]:
                continue
            repository = db.scalar(select(Repository).where(Repository.full_name == case["repository"]))
            if repository is None:
                raise SystemExit(f"Index {case['repository']} before evaluation.")
            snapshot = db.scalar(select(Snapshot).where(Snapshot.repository_id == repository.id,
                                                        Snapshot.status == "COMPLETED")
                                 .order_by(Snapshot.completed_at.desc()).limit(1))
            if snapshot is None:
                raise SystemExit(f"Index {case['repository']} before evaluation.")
            question = case["question"]
            lexical = lexical_search(db, snapshot.id, question, args.k * 3)
            vector = vector_search(db, snapshot.id, embeddings.embed_query(question), args.k * 3)
            hybrid = reciprocal_rank_fusion([vector, lexical])
            ranked = {"lexical": lexical, "vector": vector, "hybrid": hybrid,
                      "hybrid_rerank": rerank(question, hybrid)}
            relevant = {item["path"] for item in case["relevant_sources"]}
            for name, candidates in ranked.items():
                paths = list(dict.fromkeys(candidate.source.path for candidate in candidates))
                methods[name].append(score(paths, relevant, args.k))
    report = {"dataset": args.dataset.name, "questions": len(cases), "k": args.k,
              "embedding_model": settings.embedding_model,
              "methods": {name: {metric: round(sum(run[metric] for run in runs) / len(runs), 4)
                                 for metric in runs[0]} if runs else {}
                          for name, runs in methods.items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown = [f"# Retrieval evaluation", "", f"Dataset: {report['dataset']}",
                f"Questions: {report['questions']}", f"K: {args.k}", "",
                "| Method | Recall | Precision | MRR | nDCG |",
                "| --- | ---: | ---: | ---: | ---: |"]
    for name, metrics in report["methods"].items():
        markdown.append(f"| {name} | {metrics.get('recall_at_k', 0):.3f} | "
                        f"{metrics.get('precision_at_k', 0):.3f} | {metrics.get('mrr_at_k', 0):.3f} | "
                        f"{metrics.get('ndcg_at_k', 0):.3f} |")
    args.output.with_suffix(".md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print("\n".join(markdown))


if __name__ == "__main__":
    main()
