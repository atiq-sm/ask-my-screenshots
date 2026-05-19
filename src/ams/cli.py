from __future__ import annotations

import argparse
import json
import sys

from .ingest import index_folder
from .query import search
from .watch import watch_folder


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="screenshot-search")
    subparsers = parser.add_subparsers(dest="command")

    index_cmd = subparsers.add_parser("index", help="Index screenshots in a folder")
    index_cmd.add_argument("folder")
    index_cmd.add_argument("--db", default="./ams.sqlite3")
    index_cmd.add_argument("--ocr-workers", type=int, default=2)

    search_cmd = subparsers.add_parser("search", help="Search indexed screenshots")
    search_cmd.add_argument("query", nargs="+")
    search_cmd.add_argument("--db", default="./ams.sqlite3")
    search_cmd.add_argument("--top-k", type=int, default=20)
    search_cmd.add_argument("--no-bm25", action="store_true")

    watch_cmd = subparsers.add_parser("watch", help="Watch folder and auto-index")
    watch_cmd.add_argument("folder")
    watch_cmd.add_argument("--db", default="./ams.sqlite3")
    watch_cmd.add_argument("--poll-seconds", type=int, default=2)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Supports: screenshot-search "that postgres connection error"
    if argv and argv[0] not in {"index", "search", "watch", "-h", "--help"}:
        argv = ["search", *argv]

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "index":
        result = index_folder(args.folder, args.db, ocr_workers=args.ocr_workers)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "search":
        query_text = " ".join(args.query)
        results = search(query_text, args.db, top_k=args.top_k, bm25=not args.no_bm25)
        for item in results:
            print(f"[{item['score']:.4f}] {item['path']}")
            print(f"  {item['caption']}")
        return 0

    if args.command == "watch":
        watch_folder(args.folder, args.db, poll_seconds=args.poll_seconds)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
