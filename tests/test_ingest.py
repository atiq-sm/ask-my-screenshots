from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ams.db import Database
from ams.ingest import index_folder
from ams.models import ModelPipeline


class FakeModels(ModelPipeline):
    def caption_image(self, image_path: str | Path) -> str:
        return f"caption {Path(image_path).stem}"

    def ocr_image(self, image_path: str | Path) -> str:
        return f"ocr {Path(image_path).stem}"

    def embed_text(self, text: str) -> list[float]:
        tokens = text.lower().split()
        return [float(tokens.count("error")), float(tokens.count("pricing")), float(len(tokens))]


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


if __name__ == "__main__":
    unittest.main()
