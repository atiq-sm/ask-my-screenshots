from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ams.ignore import is_ignored, load_amsignore
from ams.redact import redact_secrets


class IgnoreTests(unittest.TestCase):
    def test_amsignore_skips_matching_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".amsignore").write_text("private/**\n", encoding="utf-8")
            (root / "public.png").write_bytes(b"x")
            (root / "private").mkdir()
            (root / "private" / "secret.png").write_bytes(b"x")
            spec = load_amsignore(root)
            self.assertTrue(is_ignored(root / "private" / "secret.png", root, spec))
            self.assertFalse(is_ignored(root / "public.png", root, spec))


class RedactTests(unittest.TestCase):
    def test_redacts_bearer_token(self) -> None:
        text = "Authorization: Bearer abcdef1234567890"
        self.assertIn("[REDACTED]", redact_secrets(text))
        self.assertNotIn("abcdef1234567890", redact_secrets(text))

    def test_redacts_aws_key(self) -> None:
        text = "key=AKIAIOSFODNN7EXAMPLE"
        self.assertIn("[REDACTED]", redact_secrets(text))


if __name__ == "__main__":
    unittest.main()
