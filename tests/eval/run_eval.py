from __future__ import annotations

import json
from pathlib import Path

from ams.query import search


def run_eval(
    db_path: str,
    queries_path: str = "tests/eval/queries.jsonl",
    top_k: int = 5,
) -> dict:
    total = 0
    top1_hits = 0
    topk_hits = 0
    mrr_sum = 0.0

    for line in Path(queries_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        total += 1
        results = search(item["query"], db_path, top_k=top_k)
        expected = item["expected_contains"]
        rank = None
        for i, r in enumerate(results):
            if expected in r["path"]:
                rank = i + 1
                break
        if rank == 1:
            top1_hits += 1
        if rank is not None:
            topk_hits += 1
            mrr_sum += 1.0 / rank

    return {
        "total": total,
        "top1_hits": top1_hits,
        "topk_hits": topk_hits,
        "top1_accuracy": top1_hits / total if total else 0.0,
        "topk_accuracy": topk_hits / total if total else 0.0,
        "mrr": mrr_sum / total if total else 0.0,
        "top_k": top_k,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--queries", default="tests/eval/queries.jsonl")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(run_eval(args.db, args.queries, args.top_k), indent=2))
