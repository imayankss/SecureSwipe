"""Verify that a built wheel contains exactly the current API and source modules."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import BadZipFile, ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def expected_python_modules(project_root: Path = PROJECT_ROOT) -> set[str]:
    modules: set[str] = set()
    for package_root in (project_root / "api", project_root / "src"):
        modules.update(
            path.relative_to(project_root).as_posix()
            for path in package_root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return modules


def wheel_python_modules(wheel_path: Path) -> set[str]:
    try:
        with ZipFile(wheel_path) as wheel:
            return {
                name
                for name in wheel.namelist()
                if name.endswith(".py") and name.startswith(("api/", "src/"))
            }
    except (BadZipFile, OSError) as exc:
        raise RuntimeError(f"Cannot inspect wheel {wheel_path}: {type(exc).__name__}") from exc


def verify_wheel_contents(wheel_path: Path, project_root: Path = PROJECT_ROOT) -> None:
    expected = expected_python_modules(project_root)
    actual = wheel_python_modules(wheel_path)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        raise RuntimeError(
            "Wheel module inventory differs from source; "
            f"missing={missing or 'none'}; unexpected={unexpected or 'none'}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    wheel_path = args.wheel.resolve()
    if not wheel_path.is_file():
        raise SystemExit(f"Wheel not found: {wheel_path}")
    try:
        verify_wheel_contents(wheel_path)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Verified wheel module inventory: {wheel_path.name}")


if __name__ == "__main__":
    main()
