"""Wheel inventory tests prevent ignored stale build modules from shipping."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.verify_wheel_contents import verify_wheel_contents


def _write_wheel(path: Path, members: set[str]) -> None:
    with ZipFile(path, "w") as wheel:
        for member in sorted(members):
            wheel.writestr(member, "\n")


def test_wheel_inventory_accepts_exact_source_modules(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "api").mkdir(parents=True)
    (project / "src/example").mkdir(parents=True)
    (project / "api/main.py").write_text("", encoding="utf-8")
    (project / "src/example/__init__.py").write_text("", encoding="utf-8")
    wheel = tmp_path / "exact.whl"
    _write_wheel(wheel, {"api/main.py", "src/example/__init__.py", "pkg.dist-info/METADATA"})

    verify_wheel_contents(wheel, project)


@pytest.mark.parametrize("difference", ["missing", "unexpected"])
def test_wheel_inventory_rejects_source_difference(tmp_path: Path, difference: str) -> None:
    project = tmp_path / "project"
    (project / "api").mkdir(parents=True)
    (project / "src").mkdir()
    (project / "api/main.py").write_text("", encoding="utf-8")
    members = set() if difference == "missing" else {"api/main.py", "src/deleted.py"}
    wheel = tmp_path / "invalid.whl"
    _write_wheel(wheel, members)

    with pytest.raises(RuntimeError, match=difference):
        verify_wheel_contents(wheel, project)
