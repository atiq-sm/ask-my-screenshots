from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import struct
import urllib.request
from pathlib import Path

from .config import AppConfig
from .redact import redact_secrets

CAPTION_PROMPT = (
    "Describe this screenshot in 2-3 sentences. Mention the app or website, "
    "what is on screen, and any visible error text."
)
CAPTION_PROMPT_SHORT = "Describe this screenshot in 2-3 sentences."

_COORD_CAPTION = re.compile(r"^\s*\[?\s*\d+\.\d+")

_paddle_ocr_engine = None
_tesseract_configured = False

WINDOWS_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _ensure_tesseract_cmd() -> None:
    global _tesseract_configured
    if _tesseract_configured:
        return
    import pytesseract

    env = os.environ.get("TESSERACT_CMD")
    if env and Path(env).is_file():
        pytesseract.pytesseract.tesseract_cmd = env
    elif os.name == "nt":
        for candidate in WINDOWS_TESSERACT_PATHS:
            if Path(candidate).is_file():
                pytesseract.pytesseract.tesseract_cmd = candidate
                break
    _tesseract_configured = True


def _serialize_f32(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


class ModelPipeline:
    def __init__(
        self,
        vlm_model: str = "qwen2-vl:7b",
        embedding_model: str = "nomic-embed-text",
        ollama_base_url: str = "http://127.0.0.1:11434",
        ocr_backend: str = "tesseract",
        ollama_timeout_seconds: int = 120,
        ocr_only: bool = False,
    ) -> None:
        self.vlm_model = vlm_model
        self.embedding_model = embedding_model
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.ocr_backend = ocr_backend.lower()
        self.ollama_timeout_seconds = ollama_timeout_seconds
        self.ocr_only = ocr_only

    @classmethod
    def from_config(cls, config: AppConfig) -> ModelPipeline:
        return cls(
            vlm_model=config.vlm_model,
            embedding_model=config.embedding_model,
            ollama_base_url=config.ollama_base_url,
            ocr_backend=config.ocr_backend,
            ollama_timeout_seconds=config.ollama_timeout_seconds,
            ocr_only=config.ocr_only,
        )

    def caption_image(self, image_path: str | Path) -> str:
        if self.ocr_only:
            return ""
        path = Path(image_path)
        stub = f"Screenshot file named '{path.stem.replace('_', ' ')}'."
        if os.environ.get("AMS_DISABLE_OLLAMA", "0") == "1":
            return stub
        response = self._ollama_chat_vision(path, CAPTION_PROMPT)
        if response and _COORD_CAPTION.match(response):
            response = self._ollama_chat_vision(path, CAPTION_PROMPT_SHORT)
        return response.strip() if response else stub

    def ocr_image(self, image_path: str | Path) -> str:
        text = ""
        if self.ocr_backend == "paddle":
            text = self._paddle_ocr(image_path)
        else:
            text = self._tesseract_ocr(image_path)
        return redact_secrets(text)

    def embed_text(self, text: str) -> list[float]:
        response = self._ollama_embeddings(text)
        if response is not None:
            return response
        return self._hash_embedding(text)

    def _tesseract_ocr(self, image_path: str | Path) -> str:
        try:
            import pytesseract
            from PIL import Image

            _ensure_tesseract_cmd()
            return pytesseract.image_to_string(Image.open(image_path)).strip()
        except Exception:
            return ""

    def _paddle_ocr(self, image_path: str | Path) -> str:
        global _paddle_ocr_engine
        try:
            if _paddle_ocr_engine is None:
                from paddleocr import PaddleOCR

                _paddle_ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            result = _paddle_ocr_engine.ocr(str(image_path), cls=True)
            lines: list[str] = []
            for block in result or []:
                for line in block or []:
                    if line and len(line) >= 2:
                        lines.append(str(line[1][0]))
            return "\n".join(lines).strip()
        except Exception:
            return self._tesseract_ocr(image_path)

    def _ollama_chat_vision(self, image_path: Path, prompt: str) -> str | None:
        try:
            image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        except OSError:
            return None

        payload = json.dumps(
            {
                "model": self.vlm_model,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_b64],
                    }
                ],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.ollama_base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.ollama_timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                message = data.get("message", {})
                content = message.get("content")
                if isinstance(content, str):
                    return content
        except Exception:
            return None
        return None

    def _ollama_embeddings(self, text: str) -> list[float] | None:
        if os.environ.get("AMS_DISABLE_OLLAMA", "0") == "1":
            return None
        payload = json.dumps({"model": self.embedding_model, "prompt": text}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            f"{self.ollama_base_url}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
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


def serialize_embedding(vector: list[float]) -> bytes:
    return _serialize_f32(vector)
