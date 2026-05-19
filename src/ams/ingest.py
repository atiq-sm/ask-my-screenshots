from __future__ import annotations

import io
import os
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from .config import AppConfig
from .db import Database, ScreenshotRecord
from .ignore import is_ignored, load_amsignore
from .models import ModelPipeline

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}


def _create_thumbnail_blob(
    image_path: Path, size: int = 256
) -> bytes | None:
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            img.thumbnail((size, size))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            return buf.getvalue()
    except Exception:
        return None


def find_images(
    folder: str | Path,
    recursive: bool = True,
) -> list[Path]:
    root = Path(folder).expanduser()
    if not root.exists():
        return []
    ignore_spec = load_amsignore(root)
    if recursive:
        candidates = root.rglob("*")
    else:
        candidates = root.glob("*")
    images = []
    for p in candidates:
        if not p.is_file() or p.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if is_ignored(p, root, ignore_spec):
            continue
        images.append(p)
    return sorted(images)


def _index_one(
    image: Path,
    mtime: float,
    db: Database,
    model_pipeline: ModelPipeline,
    thumbnail_size: int,
    caption: str,
    ocr_text: str,
) -> bool:
    text_for_embedding = f"{caption}\n{ocr_text}".strip()
    embedding = model_pipeline.embed_text(text_for_embedding)
    thumbnail_blob = _create_thumbnail_blob(image, size=thumbnail_size)
    return db.insert_record(
        ScreenshotRecord(
            path=str(image),
            mtime=mtime,
            caption=caption,
            ocr_text=ocr_text,
            embedding=embedding,
            thumbnail_blob=thumbnail_blob,
            embedding_model=model_pipeline.embedding_model,
        )
    )


def index_single(
    image_path: str | Path,
    db_path: str | Path,
    model_pipeline: ModelPipeline | None = None,
    config: AppConfig | None = None,
) -> dict:
    config = config or AppConfig()
    model_pipeline = model_pipeline or ModelPipeline.from_config(config)
    image = Path(image_path).expanduser()
    if not image.is_file() or image.suffix.lower() not in IMAGE_SUFFIXES:
        return {"indexed": 0, "skipped": 0, "path": str(image)}

    mtime = os.path.getmtime(image)
    db = Database(db_path)
    try:
        if db.is_indexed(str(image), mtime):
            return {"indexed": 0, "skipped": 1, "path": str(image)}
        caption = model_pipeline.caption_image(image)
        ocr_text = model_pipeline.ocr_image(image)
        inserted = _index_one(
            image,
            mtime,
            db,
            model_pipeline,
            config.thumbnail_size,
            caption,
            ocr_text,
        )
        return {"indexed": int(inserted), "skipped": 0, "path": str(image)}
    finally:
        db.close()


def index_folder(
    folder: str | Path,
    db_path: str | Path,
    model_pipeline: ModelPipeline | None = None,
    config: AppConfig | None = None,
    ocr_workers: int | None = None,
) -> dict:
    config = config or AppConfig()
    workers = ocr_workers if ocr_workers is not None else config.ocr_workers
    if workers < 1:
        raise ValueError("ocr_workers must be >= 1")

    model_pipeline = model_pipeline or ModelPipeline.from_config(config)
    db = Database(db_path)
    try:
        images = find_images(folder, recursive=config.watch_recursive)
        to_index: list[tuple[Path, float]] = []
        skipped = 0
        for image in images:
            mtime = os.path.getmtime(image)
            if db.is_indexed(str(image), mtime):
                skipped += 1
            else:
                to_index.append((image, mtime))

        indexed = 0
        with ThreadPoolExecutor(max_workers=workers) as ocr_pool, ThreadPoolExecutor(
            max_workers=max(1, config.vlm_workers)
        ) as vlm_pool:
            ocr_futures: dict[Path, Future[str]] = {
                image: ocr_pool.submit(model_pipeline.ocr_image, image)
                for image, _ in to_index
            }
            vlm_futures: dict[Path, Future[str]] = {}
            if not model_pipeline.ocr_only:
                vlm_futures = {
                    image: vlm_pool.submit(model_pipeline.caption_image, image)
                    for image, _ in to_index
                }

            for image, mtime in to_index:
                ocr_text = ocr_futures[image].result() or ""
                caption = ""
                if model_pipeline.ocr_only:
                    caption = ""
                elif image in vlm_futures:
                    caption = vlm_futures[image].result() or ""
                inserted = _index_one(
                    image,
                    mtime,
                    db,
                    model_pipeline,
                    config.thumbnail_size,
                    caption,
                    ocr_text,
                )
                if inserted:
                    indexed += 1

        return {
            "scanned": len(images),
            "indexed": indexed,
            "skipped": skipped,
            "db_path": str(db_path),
        }
    finally:
        db.close()
