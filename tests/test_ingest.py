from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import os

from ams.db import Database
from ams.ingest import find_images, index_folder
from ams.models import ModelPipeline

os.environ.setdefault("AMS_TEST_NO_VEC", "1")


class FakeModels(ModelPipeline):
    def caption_image(self, image_path: str | Path) -> str:
        return f"caption {Path(image_path).stem}"

    def ocr_image(self, image_path: str | Path) -> str:
        return f"ocr {Path(image_path).stem}"

    def embed_text(self, text: str) -> list[float]:
        tokens = text.lower().split()
        vector = [0.0] * 64
        vector[0] = float(tokens.count("error"))
        vector[1] = float(tokens.count("pricing"))
        vector[2] = float(len(tokens))
        return vector


class IngestTests(unittest.TestCase):
    def test_index_is_idempotent_for_same_path_and_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "one.png").write_bytes(b"fake")
            (root / "two.png").write_bytes(b"fake")
            db_path = root / "ams.sqlite3"

            first = index_folder(root, db_path, model_pipeline=FakeModels(), ocr_workers=2)
            second = index_folder(root, db_path, model_pipeline=FakeModels(), ocr_workers=2)

            self.assertEqual(first["indexed"], 2)
            self.assertEqual(second["indexed"], 0)
            self.assertEqual(second["skipped"], 2)

            db = Database(db_path)
            try:
                self.assertEqual(db.count(), 2)
            finally:
                db.close()

    def test_amsignore_excludes_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".amsignore").write_text("skip.png\n", encoding="utf-8")
            (root / "keep.png").write_bytes(b"fake")
            (root / "skip.png").write_bytes(b"fake")
            images = find_images(root)
            names = {p.name for p in images}
            self.assertIn("keep.png", names)
            self.assertNotIn("skip.png", names)


if __name__ == "__main__":
    unittest.main()
