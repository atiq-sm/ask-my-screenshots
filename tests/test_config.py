from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ams.config import AppConfig, load_config


class ConfigTests(unittest.TestCase):
    def test_loads_toml(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.toml"
            path.write_text(
                """
[models]
vlm = "llava"
embedding = "nomic-embed-text"
ocr = "tesseract"

[index]
ocr_workers = 4
ocr_only = true
""",
                encoding="utf-8",
            )
            cfg = load_config(path)
            self.assertEqual(cfg.vlm_model, "llava")
            self.assertEqual(cfg.ocr_workers, 4)
            self.assertTrue(cfg.ocr_only)

    def test_defaults(self) -> None:
        cfg = AppConfig()
        self.assertEqual(cfg.embedding_model, "nomic-embed-text")
        self.assertIn("ams", cfg.db_path.replace("\\", "/").lower())


if __name__ == "__main__":
    unittest.main()
