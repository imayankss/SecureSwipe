"""Utilities for loading and reading the project YAML configuration."""

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from src.utils.paths import resolve_path

DEFAULT_CONFIG_PATH = "configs/config.yaml"


def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load the project YAML configuration file.

    Args:
        config_path: Path to the config file, relative to the project root
            (or absolute). Defaults to ``configs/config.yaml``.

    Returns:
        Dict[str, Any]: The parsed configuration as a dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist at the
            resolved path.
        ValueError: If the config file exists but is not valid YAML, or
            does not parse to a dictionary.
    """
    resolved_path: Path = resolve_path(config_path)

    if not resolved_path.exists():
        raise FileNotFoundError(
            f"Config file not found at '{resolved_path}'. "
            f"Expected a YAML file at '{config_path}' relative to the "
            "project root."
        )

    try:
        with resolved_path.open("r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
    except yaml.YAMLError as error:
        raise ValueError(
            f"Failed to parse YAML config file at '{resolved_path}': {error}"
        ) from error

    if not isinstance(config, dict):
        raise ValueError(
            f"Config file at '{resolved_path}' did not parse to a dictionary. "
            f"Got type: {type(config).__name__}."
        )

    return config


def get_config_value(
    config: Dict[str, Any],
    dotted_key: str,
    default: Optional[Any] = None,
) -> Any:
    """Retrieve a value from a config dictionary using a dotted key path.

    Example:
        get_config_value(config, "project.name")

    Args:
        config: The configuration dictionary, typically from ``load_config``.
        dotted_key: A dot-separated key path, e.g. ``"project.name"``.
        default: Value to return if the key path is not found.

    Returns:
        Any: The value found at the dotted key path, or ``default`` if any
        part of the path is missing.
    """
    keys = dotted_key.split(".")
    current: Any = config

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current