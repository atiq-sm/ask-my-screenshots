from __future__ import annotations

import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import AppConfig
from .ingest import IMAGE_SUFFIXES, index_single
from .models import ModelPipeline

MIN_DEBOUNCE_SECONDS = 0.5


class DebouncedIndexer(FileSystemEventHandler):
    def __init__(
        self,
        db_path: str,
        config: AppConfig,
        model_pipeline: ModelPipeline,
    ) -> None:
        self.db_path = db_path
        self.config = config
        self.model_pipeline = model_pipeline
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: str) -> None:
        debounce = max(MIN_DEBOUNCE_SECONDS, self.config.watch_debounce_seconds)

        def run() -> None:
            result = index_single(
                path,
                self.db_path,
                model_pipeline=self.model_pipeline,
                config=self.config,
            )
            if result.get("indexed"):
                print(f"Indexed: {path}")

        with self._lock:
            existing = self._timers.pop(path, None)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(debounce, run)
            self._timers[path] = timer
            timer.start()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._maybe_index(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._maybe_index(event.src_path)

    def _maybe_index(self, src_path: str) -> None:
        path = Path(src_path)
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            return
        self._schedule(str(path.resolve()))


def watch_folder(
    folder: str,
    db_path: str,
    config: AppConfig | None = None,
    model_pipeline: ModelPipeline | None = None,
) -> None:
    config = config or AppConfig()
    model_pipeline = model_pipeline or ModelPipeline.from_config(config)
    root = Path(folder).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    handler = DebouncedIndexer(db_path, config, model_pipeline)
    observer = Observer()
    observer.schedule(handler, str(root), recursive=config.watch_recursive)
    observer.start()
    print(f"Watching {root} (debounce {config.watch_debounce_seconds}s)")
    try:
        observer.join()
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
