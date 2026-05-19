from __future__ import annotations

import argparse
import json
import sys

from .config import AppConfig, load_config
from .ingest import index_folder
from .models import ModelPipeline
from .query import search
from .tui import run_tui
from .watch import watch_folder


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="screenshot-search")
    parser.add_argument(
        "--config",
        help="Path to config.toml (default: ./config.toml or AMS_CONFIG)",
    )
    subparsers = parser.add_subparsers(dest="command")

    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--config", help="Path to config.toml")

    index_cmd = subparsers.add_parser(
        "index", help="Index screenshots in a folder", parents=[parent]
    )
    index_cmd.add_argument(
        "folder",
        nargs="?",
        help="Screenshot folder (default from config)",
    )
    index_cmd.add_argument("--db", help="SQLite database path")
    index_cmd.add_argument("--ocr-workers", type=int)
    index_cmd.add_argument(
        "--ocr-only",
        action="store_true",
        help="Skip VLM captions; OCR + embed only (faster, CPU-friendly)",
    )

    search_cmd = subparsers.add_parser(
        "search", help="Search indexed screenshots", parents=[parent]
    )
    search_cmd.add_argument("query", nargs="+")
    search_cmd.add_argument("--db", help="SQLite database path")
    search_cmd.add_argument("--top-k", type=int, default=20)
    search_cmd.add_argument("--no-bm25", action="store_true")
    search_cmd.add_argument("--json", action="store_true", dest="as_json")

    watch_cmd = subparsers.add_parser(
        "watch", help="Watch folder and auto-index", parents=[parent]
    )
    watch_cmd.add_argument("folder", nargs="?")
    watch_cmd.add_argument("--db", help="SQLite database path")

    tui_cmd = subparsers.add_parser("tui", help="Interactive search UI", parents=[parent])
    tui_cmd.add_argument("--db", help="SQLite database path")

    return parser


def _resolve_config(args: argparse.Namespace) -> AppConfig:
    config = load_config(args.config)
    if getattr(args, "ocr_only", False):
        config.ocr_only = True
    if getattr(args, "db", None):
        config.db_path = args.db
    if getattr(args, "ocr_workers", None) is not None:
        config.ocr_workers = args.ocr_workers
    return config


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if argv and argv[0] not in {
        "index",
        "search",
        "watch",
        "tui",
        "-h",
        "--help",
    }:
        argv = ["search", *argv]

    parser = _build_parser()
    args = parser.parse_args(argv)
    config = _resolve_config(args)

    if args.command == "index":
        folder = args.folder or config.screenshot_folder
        result = index_folder(
            folder,
            config.db_path,
            config=config,
            ocr_workers=config.ocr_workers,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "search":
        query_text = " ".join(args.query)
        results = search(
            query_text,
            config.db_path,
            top_k=args.top_k,
            bm25=not args.no_bm25,
            config=config,
        )
        if args.as_json:
            print(json.dumps(results, indent=2))
            return 0
        for item in results:
            print(f"[{item['score']:.4f}] {item['path']}")
            print(f"  {item['caption']}")
        return 0

    if args.command == "watch":
        folder = args.folder or config.screenshot_folder
        watch_folder(folder, config.db_path, config=config)
        return 0

    if args.command == "tui":
        run_tui(config.db_path, config=config)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
