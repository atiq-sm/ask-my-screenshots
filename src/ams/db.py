from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class ScreenshotRecord:
    path: str
    mtime: float
    caption: str
    ocr_text: str
    embedding: list[float]
    thumbnail_blob: bytes | None
    embedding_model: str


class Database:
    def __init__(self, db_path: str | Path) -> None:
        self.path = str(db_path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS screenshots (
                path TEXT NOT NULL,
                mtime REAL NOT NULL,
                caption TEXT NOT NULL,
                ocr_text TEXT NOT NULL,
                embedding TEXT NOT NULL,
                thumbnail_blob BLOB,
                embedding_model TEXT NOT NULL DEFAULT 'nomic-embed-text',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                PRIMARY KEY (path, mtime)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_screenshots_path ON screenshots(path)"
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def is_indexed(self, path: str, mtime: float) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM screenshots WHERE path = ? AND mtime = ? LIMIT 1", (path, mtime)
        ).fetchone()
        return row is not None

    def insert_record(self, record: ScreenshotRecord) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO screenshots(path, mtime, caption, ocr_text, embedding, thumbnail_blob, embedding_model)
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
        self.conn.commit()
        return cur.rowcount > 0

    def iter_records(self) -> Iterable[ScreenshotRecord]:
        rows = self.conn.execute(
            "SELECT path, mtime, caption, ocr_text, embedding, thumbnail_blob, embedding_model FROM screenshots"
        ).fetchall()
        for row in rows:
            yield ScreenshotRecord(
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

    def query_by_embedding(self, query_embedding: list[float], top_k: int = 20) -> list[dict]:
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
