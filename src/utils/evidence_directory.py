"""Atomic publication boundary for multi-file evidence runs."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def require_absent_evidence_target(target: str | Path) -> Path:
    """Reject every existing target, including empty directories and symlinks."""
    path = Path(target)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite evidence target: {path}")
    if not path.name or path.name in {".", ".."}:
        raise ValueError("Evidence target must name a new child directory.")
    return path


@contextmanager
def atomic_evidence_directory(target: str | Path) -> Iterator[Path]:
    """Yield a sibling temporary directory and atomically publish on success.

    A failure removes the temporary tree and leaves ``target`` absent. If a
    concurrent writer creates ``target``, publication fails without modifying it.
    """
    path = require_absent_evidence_target(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{path.name}.", dir=path.parent))
    try:
        yield temporary
        require_absent_evidence_target(path)
        temporary.rename(path)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
