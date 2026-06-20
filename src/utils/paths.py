"""Centralized project path handling utilities.

All path operations in this project should go through this module so that
path logic stays consistent and free of hardcoded, machine-specific paths.
"""

from pathlib import Path
from typing import Iterable, Union

PathLike = Union[str, Path]


def get_project_root() -> Path:
    """Return the absolute path to the project root directory.

    The project root is resolved relative to this file's location
    (``<root>/src/utils/paths.py``), so this works regardless of the
    current working directory the project is run from.

    Returns:
        Path: Absolute path to the project root directory.
    """
    return Path(__file__).resolve().parents[2]


def resolve_path(path: PathLike) -> Path:
    """Resolve a path relative to the project root.

    If ``path`` is already absolute, it is returned unchanged (as a
    ``Path`` object). If it is relative, it is resolved against the
    project root directory.

    Args:
        path: A relative or absolute path.

    Returns:
        Path: The resolved absolute path.
    """
    path_obj = Path(path)

    if path_obj.is_absolute():
        return path_obj

    return (get_project_root() / path_obj).resolve()


def ensure_directory(path: PathLike) -> Path:
    """Ensure a directory exists, creating it (and parents) if needed.

    Args:
        path: Relative or absolute path to the directory.

    Returns:
        Path: The resolved, guaranteed-to-exist directory path.
    """
    directory = resolve_path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def ensure_directories(paths: Iterable[PathLike]) -> Iterable[Path]:
    """Ensure multiple directories exist, creating each if needed.

    Args:
        paths: An iterable of relative or absolute directory paths.

    Returns:
        Iterable[Path]: The resolved, guaranteed-to-exist directory paths,
        in the same order as the input.
    """
    return [ensure_directory(path) for path in paths]