from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .db import Database, ScreenshotRecord
from .models import ModelPipeline

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
DEFAULT_THUMBNAIL_SIZE = (256, 256)


def _create_thumbnail_blob(
    image_path: Path, size: tuple[int, int] = DEFAULT_THUMBNAIL_SIZE
) -> bytes | None:
    try:
        from PIL import Image  # type: ignore

        with Image.open(image_path) as img:
            img.thumbnail(size)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            return buf.getvalue()
    except Exception:
        return None


def find_images(folder: str | Path) -> list[Path]:
    root = Path(folder).expanduser()
    if not root.exists():
        return []
    return sorted(
        [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    )


def index_folder(
    folder: str | Path,
    db_path: str | Path,
    model_pipeline: ModelPipeline | None = None,
    ocr_workers: int = 2,
) -> dict:
    model_pipeline = model_pipeline or ModelPipeline()
    db = Database(db_path)
    try:
        images = find_images(folder)
        to_index: list[tuple[Path, float]] = []
        skipped = 0
        for image in images:
            mtime = os.path.getmtime(image)
            if db.is_indexed(str(image), mtime):
                skipped += 1
            else:
                to_index.append((image, mtime))

        indexed = 0
        with ThreadPoolExecutor(max_workers=max(1, ocr_workers)) as ocr_pool:
            ocr_futures = {
                image: ocr_pool.submit(model_pipeline.ocr_image, image) for image, _ in to_index
            }
            for image, mtime in to_index:
                caption = model_pipeline.caption_image(image)
                ocr_text = ocr_futures[image].result() or ""
                text_for_embedding = f"{caption}\n{ocr_text}".strip()
                embedding = model_pipeline.embed_text(text_for_embedding)
                thumbnail_blob = _create_thumbnail_blob(image)
                inserted = db.insert_record(
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
