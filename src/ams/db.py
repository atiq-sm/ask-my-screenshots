from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import serialize_embedding


@dataclass
class ScreenshotRecord:
    path: str
    mtime: float
    caption: str
    ocr_text: str
    embedding: list[float]
    thumbnail_blob: bytes | None
    embedding_model: str
    record_id: int | None = None


class Database:
    def __init__(self, db_path: str | Path) -> None:
        self.path = str(db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._vec_enabled = False
        self._embedding_dim: int | None = None
        self._init_schema()
        self._try_load_vec()

    def _try_load_vec(self) -> None:
        if os.environ.get("AMS_TEST_NO_VEC", "0") == "1":
            return
        try:
            import sqlite_vec

            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)
            self._vec_enabled = True
            if self._embedding_dim is not None:
                self._ensure_vec_table()
        except Exception:
            self._vec_enabled = False

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                mtime REAL NOT NULL,
                caption TEXT NOT NULL,
                ocr_text TEXT NOT NULL,
                embedding TEXT NOT NULL,
                thumbnail_blob BLOB,
                embedding_model TEXT NOT NULL DEFAULT 'nomic-embed-text',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(path, mtime)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_screenshots_path ON screenshots(path)"
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = 'embedding_dim'"
        ).fetchone()
        if row:
            self._embedding_dim = int(row["value"])

    def _ensure_vec_table(self) -> None:
        if self._embedding_dim is None:
            return
        dim = self._embedding_dim
        exists = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'screenshot_embeddings'"
        ).fetchone()
        if exists:
            return
        self.conn.execute(
            f"""
            CREATE VIRTUAL TABLE screenshot_embeddings USING vec0(
                embedding float[{dim}]
            )
            """
        )
        self.conn.commit()

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def _register_embedding_dim(self, dim: int) -> None:
        if self._embedding_dim is None:
            self._embedding_dim = dim
            self._set_meta("embedding_dim", str(dim))
            if self._vec_enabled:
                self._ensure_vec_table()
        elif self._embedding_dim != dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self._embedding_dim}, got {dim}"
            )

    def close(self) -> None:
        self.conn.close()

    def is_indexed(self, path: str, mtime: float) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM screenshots WHERE path = ? AND mtime = ? LIMIT 1",
            (path, mtime),
        ).fetchone()
        return row is not None

    def insert_record(self, record: ScreenshotRecord) -> bool:
        dim = len(record.embedding)
        self._register_embedding_dim(dim)

        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO screenshots(
                path, mtime, caption, ocr_text, embedding,
                thumbnail_blob, embedding_model
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.path,
                record.mtime,
                record.caption,
                record.ocr_text,
                json.dumps(record.embedding),
                record.thumbnail_blob,
                record.embedding_model,
            ),
        )
        if cur.rowcount == 0:
            self.conn.commit()
            return False

        record_id = int(cur.lastrowid)
        if self._vec_enabled and self._embedding_dim:
            blob = serialize_embedding(record.embedding)
            self.conn.execute(
                "INSERT INTO screenshot_embeddings(rowid, embedding) VALUES (?, ?)",
                (record_id, blob),
            )
        self.conn.commit()
        return True

    def iter_records(self) -> Iterable[ScreenshotRecord]:
        rows = self.conn.execute(
            """
            SELECT id, path, mtime, caption, ocr_text, embedding,
                   thumbnail_blob, embedding_model
            FROM screenshots
            """
        ).fetchall()
        for row in rows:
            yield ScreenshotRecord(
                record_id=row["id"],
                path=row["path"],
                mtime=row["mtime"],
                caption=row["caption"],
                ocr_text=row["ocr_text"],
                embedding=json.loads(row["embedding"]),
                thumbnail_blob=row["thumbnail_blob"],
                embedding_model=row["embedding_model"],
            )

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0])

    def get_by_path(self, path: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT path, caption, ocr_text, thumbnail_blob
            FROM screenshots
            WHERE path = ?
            ORDER BY mtime DESC
            LIMIT 1
            """,
            (path,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def query_by_embedding(
        self, query_embedding: list[float], top_k: int = 20
    ) -> list[dict]:
        if self._vec_enabled and self._embedding_dim:
            return self._query_vec(query_embedding, top_k)
        return self._query_brute_force(query_embedding, top_k)

    def _query_vec(self, query_embedding: list[float], top_k: int) -> list[dict]:
        if len(query_embedding) != self._embedding_dim:
            raise ValueError(
                f"Query embedding dim {len(query_embedding)} != stored {self._embedding_dim}"
            )
        blob = serialize_embedding(query_embedding)
        rows = self.conn.execute(
            """
            SELECT s.path, s.caption, s.ocr_text, e.distance
            FROM screenshot_embeddings e
            JOIN screenshots s ON s.id = e.rowid
            WHERE e.embedding MATCH ?
              AND k = ?
            ORDER BY e.distance
            """,
            (blob, top_k),
        ).fetchall()
        results = []
        for row in rows:
            distance = float(row["distance"])
            similarity = 1.0 / (1.0 + distance)
            results.append(
                {
                    "path": row["path"],
                    "caption": row["caption"],
                    "ocr_text": row["ocr_text"],
                    "similarity": similarity,
                    "score": similarity,
                }
            )
        return results

    def _query_brute_force(
        self, query_embedding: list[float], top_k: int
    ) -> list[dict]:
        scored = []
        for row in self.conn.execute(
            "SELECT path, caption, ocr_text, embedding FROM screenshots"
        ).fetchall():
            emb = json.loads(row["embedding"])
            similarity = cosine_similarity(query_embedding, emb)
            scored.append(
                {
                    "path": row["path"],
                    "caption": row["caption"],
                    "ocr_text": row["ocr_text"],
                    "similarity": similarity,
                    "score": similarity,
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    length = min(len(a), len(b))
    a2 = a[:length]
    b2 = b[:length]
    dot = sum(x * y for x, y in zip(a2, b2))
    na = math.sqrt(sum(x * x for x in a2))
    nb = math.sqrt(sum(y * y for y in b2))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
