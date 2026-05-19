from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

from ams.config import AppConfig
from ams.db import Database
from ams.ingest import index_folder
from ams.query import search


def _db_size_mb(db_path: Path) -> float:
    return db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0.0


def run_benchmarks(
    folder: str,
    db_path: str,
    query: str = "postgres connection error",
    query_runs: int = 100,
    ocr_only: bool = False,
) -> dict:
    os.environ.setdefault("AMS_TEST_NO_VEC", "0")
    folder_path = Path(folder).expanduser()
    db = Path(db_path)
    if db.exists():
        db.unlink()

    config = AppConfig(ocr_only=ocr_only)
    config.db_path = str(db)

    t0 = time.perf_counter()
    stats = index_folder(folder_path, config.db_path, config=config)
    index_seconds = time.perf_counter() - t0
    indexed = max(stats.get("indexed", 0), 1)
    imgs_per_min = (indexed / index_seconds) * 60 if index_seconds > 0 else 0.0

    latencies: list[float] = []
    for _ in range(query_runs):
        t1 = time.perf_counter()
        search(query, config.db_path, top_k=20, config=config)
        latencies.append((time.perf_counter() - t1) * 1000)

    database = Database(config.db_path)
    try:
        count = database.count()
    finally:
        database.close()

    size_mb = _db_size_mb(db)
    per_1k_mb = (size_mb / count) * 1000 if count else 0.0

    return {
        "folder": str(folder_path),
        "ocr_only": ocr_only,
        "indexed": indexed,
        "index_seconds": round(index_seconds, 2),
        "images_per_minute": round(imgs_per_min, 2),
        "query_ms_p50": round(statistics.median(latencies), 2),
        "query_ms_p95": round(
            sorted(latencies)[int(0.95 * len(latencies)) - 1] if latencies else 0, 2
        ),
        "db_size_mb": round(size_mb, 3),
        "db_mb_per_1k_images": round(per_1k_mb, 3),
        "record_count": count,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark indexing and query latency")
    parser.add_argument("--folder", required=True, help="Folder of screenshots to index")
    parser.add_argument("--db", default="./benchmark.sqlite3")
    parser.add_argument("--query", default="postgres connection error")
    parser.add_argument("--ocr-only", action="store_true")
    parser.add_argument("--runs", type=int, default=100)
    args = parser.parse_args()
    result = run_benchmarks(
        args.folder, args.db, args.query, args.runs, ocr_only=args.ocr_only
    )
    print(json.dumps(result, indent=2))
