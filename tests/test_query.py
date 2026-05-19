from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import os

from ams.ingest import index_folder
from ams.models import ModelPipeline
from ams.query import search

os.environ.setdefault("AMS_TEST_NO_VEC", "1")


class FakeModels(ModelPipeline):
    def caption_image(self, image_path: str | Path) -> str:
        return Path(image_path).stem.replace("_", " ")

    def ocr_image(self, image_path: str | Path) -> str:
        return Path(image_path).stem.replace("_", " ")

    def embed_text(self, text: str) -> list[float]:
        text = text.lower()
        return [
            float("postgres" in text or "database" in text),
            float("error" in text or "failed" in text),
            float("pricing" in text),
            float("bar" in text or "chart" in text),
        ]


class QueryTests(unittest.TestCase):
    def test_returns_most_relevant_result_first(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "postgres_connection_error.png").write_bytes(b"fake")
            (root / "pricing_slide_bar_chart.png").write_bytes(b"fake")
            (root / "random_meme.png").write_bytes(b"fake")
            db_path = root / "ams.sqlite3"

            models = FakeModels()
            index_folder(root, db_path, model_pipeline=models)

            results = search(
                "that postgres connection error",
                str(db_path),
                top_k=3,
                bm25=True,
                model_pipeline=models,
            )

            self.assertGreaterEqual(len(results), 1)
            self.assertTrue(results[0]["path"].endswith("postgres_connection_error.png"))


if __name__ == "__main__":
    unittest.main()
