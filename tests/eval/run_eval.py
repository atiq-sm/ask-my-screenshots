from __future__ import annotations

import json
from pathlib import Path

from ams.query import search


def run_eval(db_path: str, queries_path: str = "tests/eval/queries.jsonl", top_k: int = 5) -> dict:
    total = 0
    hits = 0
    for line in Path(queries_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        total += 1
        results = search(item["query"], db_path, top_k=top_k)
        if any(item["expected_contains"] in r["path"] for r in results):
            hits += 1
    return {"total": total, "hits": hits, "top_k_accuracy": hits / total if total else 0.0}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--queries", default="tests/eval/queries.jsonl")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    print(run_eval(args.db, args.queries, args.top_k))
