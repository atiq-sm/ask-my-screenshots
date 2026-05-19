# Benchmarks

**Hardware:** Windows 10, consumer GPU via Ollama  
**Models:** `llava:7b` (VLM), `nomic-embed-text` (embeddings), Tesseract 5.4  
**Dataset:** 23 screenshots in `tests/test screenshots` (lab safety training quizzes)

## Results

| Mode | Images | Index time | Throughput | Query p50 | Query p95 | DB size | MB / 1k imgs |
|------|--------|------------|------------|-----------|-----------|---------|--------------|
| VLM + OCR (llava + Tesseract) | 23 | 264 s | **5.2 img/min** | 32 ms | 53 ms | 3.57 MB | ~155 |

## Index quality (after full re-index)

| Metric | Value |
|--------|-------|
| Filename-only caption stubs | **0** / 23 |
| Screenshots with OCR text (>20 chars) | **22** / 23 |

## Eval (run on matching fixture folder)

```bash
screenshot-search index ./fixtures --db ./eval.sqlite3
python tests/eval/run_eval.py --db ./eval.sqlite3
```

| Metric | Value |
|--------|-------|
| top-1 accuracy | _(run on labeled fixture)_ |
| top-5 accuracy | _(run on labeled fixture)_ |
| MRR | _(run on labeled fixture)_ |

## Reproduce

```bash
pip install -e .
# Install Tesseract (Windows): winget install UB-Mannheim.TesseractOCR
ollama pull llava:7b
ollama pull nomic-embed-text

screenshot-search index --config config.toml
python benchmarks/run_benchmarks.py --folder "tests/test screenshots" --db ./bench.sqlite3
python scripts/verify_db.py test-ams.sqlite3
```
