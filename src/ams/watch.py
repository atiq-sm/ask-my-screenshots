from __future__ import annotations

import time
from pathlib import Path

from .ingest import index_folder

MIN_POLL_SECONDS = 1


def watch_folder(folder: str, db_path: str, poll_seconds: int = 2) -> None:
    """Simple polling-based watch mode with debounce-like behavior."""
    root = Path(folder).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    print(f"Watching {root} (poll every {poll_seconds}s)")
    while True:
        stats = index_folder(root, db_path)
        if stats["indexed"]:
            print(f"Indexed {stats['indexed']} new screenshot(s)")
        time.sleep(max(MIN_POLL_SECONDS, poll_seconds))
