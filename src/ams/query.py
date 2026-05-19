from __future__ import annotations

import math
import re

from .db import Database
from .models import ModelPipeline


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def _bm25_boost(query: str, docs: list[dict]) -> dict[str, float]:
    terms = _tokenize(query)
    if not terms:
        return {d["path"]: 0.0 for d in docs}

    doc_tokens = {d["path"]: _tokenize(d.get("ocr_text", "")) for d in docs}
    df: dict[str, int] = {}
    for t in set(terms):
        df[t] = sum(1 for toks in doc_tokens.values() if t in toks)

    avgdl = sum(len(toks) for toks in doc_tokens.values()) / max(len(doc_tokens), 1)
    k1 = 1.2
    b = 0.75
    boosts: dict[str, float] = {}

    for d in docs:
        toks = doc_tokens[d["path"]]
        dl = len(toks) or 1
        score = 0.0
        for t in terms:
            tf = toks.count(t)
            if tf == 0:
                continue
            n_docs = len(docs)
            idf = math.log((n_docs - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5) + 1)
            denom = tf + k1 * (1 - b + b * (dl / max(avgdl, 1)))
            score += idf * ((tf * (k1 + 1)) / denom)
        boosts[d["path"]] = score
    return boosts


def search(
    query: str,
    db_path: str,
    top_k: int = 20,
    bm25: bool = True,
    model_pipeline: ModelPipeline | None = None,
) -> list[dict]:
    model_pipeline = model_pipeline or ModelPipeline()
    db = Database(db_path)
    try:
        query_embedding = model_pipeline.embed_text(query)
        hits = db.query_by_embedding(query_embedding, top_k=top_k)
        if not hits:
            return []

        if bm25:
            boosts = _bm25_boost(query, hits)
            for hit in hits:
                hit["score"] = hit["similarity"] + (0.2 * boosts.get(hit["path"], 0.0))

        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:top_k]
    finally:
        db.close()
