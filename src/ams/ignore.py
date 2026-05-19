from __future__ import annotations

from pathlib import Path

import pathspec

AMSIGNORE_FILENAME = ".amsignore"


def load_amsignore(root: Path) -> pathspec.PathSpec | None:
    ignore_file = root / AMSIGNORE_FILENAME
    if not ignore_file.is_file():
        return None
    patterns = [
        line.strip()
        for line in ignore_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not patterns:
        return None
    return pathspec.GitIgnoreSpec.from_lines(patterns)


def is_ignored(path: Path, root: Path, spec: pathspec.PathSpec | None) -> bool:
    if spec is None:
        return False
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    return spec.match_file(rel)
