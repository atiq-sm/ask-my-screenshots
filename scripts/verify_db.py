"""Quick DB stats after indexing."""
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else "test-ams.sqlite3"
c = sqlite3.connect(db)
total = c.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
stubs = c.execute(
    "SELECT COUNT(*) FROM screenshots WHERE caption LIKE 'Screenshot file named%'"
).fetchone()[0]
ocr_ok = c.execute(
    "SELECT COUNT(*) FROM screenshots WHERE length(ocr_text) > 20"
).fetchone()[0]
print(f"total={total} filename_stubs={stubs} ocr_nonempty={ocr_ok}")
