"""Atomic, non-overwriting JSON evidence writes for offline monitoring."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


def write_report(report: Mapping[str, Any], output: Path, *, check: bool) -> None:
    content = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if check:
        if not output.is_file() or output.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Evidence report is stale or missing: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite evidence report: {output}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
