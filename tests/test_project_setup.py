"""Day 1 setup tests: config loading, path handling, and project entry point."""

from pathlib import Path

import pytest

import main as main_module
from src.utils.config import get_config_value, load_config
from src.utils.paths import get_project_root


def test_project_root_is_valid_directory() -> None:
    """get_project_root should return an existing directory path."""
    root = get_project_root()
    assert isinstance(root, Path)
    assert root.exists()
    assert root.is_dir()


def test_config_file_exists() -> None:
    """The default config.yaml file should exist relative to the project root."""
    config_path = get_project_root() / "configs" / "config.yaml"
    assert config_path.exists()


def test_load_config_returns_dict() -> None:
    """load_config should successfully parse the YAML file into a dict."""
    config = load_config()
    assert isinstance(config, dict)
    assert "project" in config


def test_project_name_exists_in_config() -> None:
    """The config should define a non-empty project name."""
    config = load_config()
    project_name = get_config_value(config, "project.name")
    assert isinstance(project_name, str)
    assert len(project_name) > 0


def test_get_config_value_missing_key_returns_default() -> None:
    """get_config_value should return the provided default for missing keys."""
    config = load_config()
    value = get_config_value(config, "not.a.real.key", default="fallback")
    assert value == "fallback"


def test_risk_scoring_thresholds_are_valid() -> None:
    """Risk thresholds should be between 0 and 1, with low < high."""
    config = load_config()
    low_threshold = get_config_value(config, "risk_scoring.low_risk_threshold")
    high_threshold = get_config_value(config, "risk_scoring.high_risk_threshold")

    assert low_threshold is not None
    assert high_threshold is not None
    assert 0.0 <= low_threshold < high_threshold <= 1.0


def test_load_config_raises_for_missing_file() -> None:
    """load_config should raise FileNotFoundError for a nonexistent path."""
    with pytest.raises(FileNotFoundError):
        load_config(config_path="configs/does_not_exist.yaml")


def test_main_runs_safely() -> None:
    """main() should run without errors and return the loaded config."""
    result = main_module.main()
    assert isinstance(result, dict)
    assert "project" in result
