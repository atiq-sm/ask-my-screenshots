from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path


class ModelPipeline:
    def __init__(
        self,
        vlm_model: str = "qwen2-vl:7b",
        embedding_model: str = "nomic-embed-text",
        ollama_base_url: str = "http://127.0.0.1:11434",
    ) -> None:
        self.vlm_model = vlm_model
        self.embedding_model = embedding_model
        self.ollama_base_url = ollama_base_url.rstrip("/")

    def caption_image(self, image_path: str | Path) -> str:
        path = Path(image_path)
        return f"Screenshot file named '{path.stem.replace('_', ' ')}'."

    def ocr_image(self, image_path: str | Path) -> str:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore

            return pytesseract.image_to_string(Image.open(image_path)).strip()
        except Exception:
            return ""

    def embed_text(self, text: str) -> list[float]:
        response = self._ollama_embeddings(text)
        if response is not None:
            return response
        return self._hash_embedding(text)

    def _ollama_embeddings(self, text: str) -> list[float] | None:
        if os.environ.get("AMS_DISABLE_OLLAMA", "0") == "1":
            return None
        payload = json.dumps({"model": self.embedding_model, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.ollama_base_url}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                emb = data.get("embedding")
                if isinstance(emb, list) and emb:
                    return [float(v) for v in emb]
        except Exception:
            return None
        return None

    def _hash_embedding(self, text: str, dim: int = 64) -> list[float]:
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        vec = [0.0] * dim
        if not tokens:
            return vec
        for token in tokens:
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            vec[idx] += 1.0
        return vec
