# Ask My Screenshots

Local-first semantic search over your screenshot folder.

## What it does

Pipeline: **watch folder → VLM caption + OCR → embed → store → query**.

Current implementation includes:
- M1: folder indexing with idempotency on `(path, mtime)`
- M2: semantic query with optional BM25-style OCR rerank
- M3: polling-based watch mode
- repo scaffold for M4/M5 artifacts

## Quick start

```bash
python -m pip install -e .
screenshot-search index ~/Screenshots --db ./ams.sqlite3
screenshot-search "that postgres connection error" --db ./ams.sqlite3
```

## Privacy

Screenshots may contain sensitive data. Keep your DB local and add ignore/redaction rules before indexing sensitive folders.

## Development

Run tests:

```bash
python -m unittest discover -s tests -v
```
