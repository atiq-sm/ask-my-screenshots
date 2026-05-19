from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _default_screenshot_folder() -> str:
    if os.name == "nt":
        pictures = os.environ.get("USERPROFILE", "")
        if pictures:
            return str(Path(pictures) / "Pictures" / "Screenshots")
    return str(Path.home() / "Screenshots")


def _default_db_path() -> str:
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            return str(Path(local) / "ams" / "ams.sqlite3")
    return str(Path.home() / ".local" / "share" / "ams" / "ams.sqlite3")


@dataclass
class AppConfig:
    vlm_model: str = "qwen2-vl:7b"
    embedding_model: str = "nomic-embed-text"
    ocr_backend: str = "tesseract"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: int = 120
    db_path: str = field(default_factory=_default_db_path)
    screenshot_folder: str = field(default_factory=_default_screenshot_folder)
    ocr_workers: int = 2
    vlm_workers: int = 1
    thumbnail_size: int = 256
    ocr_only: bool = False
    bm25_boost_weight: float = 0.2
    watch_debounce_seconds: float = 2.0
    watch_recursive: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> AppConfig:
        models = data.get("models", {})
        index = data.get("index", {})
        query = data.get("query", {})
        watch = data.get("watch", {})
        return cls(
            vlm_model=models.get("vlm", cls.vlm_model),
            embedding_model=models.get("embedding", cls.embedding_model),
            ocr_backend=models.get("ocr", cls.ocr_backend),
            ollama_base_url=models.get("ollama_base_url", cls.ollama_base_url),
            ollama_timeout_seconds=int(
                models.get("ollama_timeout_seconds", cls.ollama_timeout_seconds)
            ),
            db_path=index.get("db_path", _default_db_path()),
            screenshot_folder=index.get(
                "screenshot_folder", _default_screenshot_folder()
            ),
            ocr_workers=int(index.get("ocr_workers", cls.ocr_workers)),
            vlm_workers=int(index.get("vlm_workers", cls.vlm_workers)),
            thumbnail_size=int(index.get("thumbnail_size", cls.thumbnail_size)),
            ocr_only=bool(index.get("ocr_only", cls.ocr_only)),
            bm25_boost_weight=float(
                query.get("bm25_boost_weight", cls.bm25_boost_weight)
            ),
            watch_debounce_seconds=float(
                watch.get("debounce_seconds", cls.watch_debounce_seconds)
            ),
            watch_recursive=bool(watch.get("recursive", cls.watch_recursive)),
        )


def find_config_path(explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    env = os.environ.get("AMS_CONFIG")
    if env:
        path = Path(env).expanduser()
        return path if path.is_file() else None
    for candidate in (
        Path.cwd() / "config.toml",
        Path.home() / ".config" / "ams" / "config.toml",
    ):
        if candidate.is_file():
            return candidate
    return None


def load_config(config_path: str | Path | None = None) -> AppConfig:
    path = find_config_path(str(config_path) if config_path else None)
    if path is None:
        return AppConfig()
    with path.open("rb") as f:
        data = tomllib.load(f)
    return AppConfig.from_dict(data)
