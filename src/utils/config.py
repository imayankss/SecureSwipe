"""Strict, typed configuration for development and historical namespaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Mapping

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.utils.paths import resolve_path

DEFAULT_CONFIG_PATH = "configs/config.yaml"


class StrictSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectSettings(StrictSettings):
    name: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    random_seed: int = Field(ge=0, le=2_147_483_647)


class DataSettings(StrictSettings):
    raw_path: Path
    interim_dir: Path
    processed_dir: Path
    target_column: Literal["Class"]
    test_size: float = Field(gt=0.0, lt=0.5)
    validation_size: float = Field(gt=0.0, lt=0.5)

    @model_validator(mode="after")
    def validate_split_sizes(self) -> "DataSettings":
        if self.test_size + self.validation_size >= 1.0:
            raise ValueError("test_size + validation_size must be below 1.0.")
        return self


class ArtifactSettings(StrictSettings):
    trusted_root: Path
    legacy_model_dir: Path
    bundles_dir: Path

    @model_validator(mode="after")
    def validate_containment(self) -> "ArtifactSettings":
        root = resolve_path(self.trusted_root)
        for path in (self.legacy_model_dir, self.bundles_dir):
            if not resolve_path(path).is_relative_to(root):
                raise ValueError("Artifact directories must be inside trusted_root.")
        return self


class ModelSettings(StrictSettings):
    baseline_model: Literal["logistic_regression"]
    development_candidates: tuple[
        Literal["logistic_regression", "random_forest", "xgboost"], ...
    ]

    @model_validator(mode="after")
    def validate_candidates(self) -> "ModelSettings":
        if not self.development_candidates or len(set(self.development_candidates)) != len(
            self.development_candidates
        ):
            raise ValueError("development_candidates must be non-empty and unique.")
        return self


class EvaluationSettings(StrictSettings):
    primary_metric: Literal["average_precision"]
    secondary_metric: Literal["roc_auc"]
    default_threshold: float = Field(ge=0.0, le=1.0)
    recall_target: float = Field(ge=0.0, le=1.0)
    development_scope: Literal["development_validation"]
    historical_scope: Literal["historical_reported_test"]


class RiskScoringSettings(StrictSettings):
    low_risk_threshold: float = Field(ge=0.0, le=1.0)
    high_risk_threshold: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_order(self) -> "RiskScoringSettings":
        if self.low_risk_threshold >= self.high_risk_threshold:
            raise ValueError("low_risk_threshold must be below high_risk_threshold.")
        return self


class ReportSettings(StrictSettings):
    figures_dir: Path
    metrics_dir: Path
    threshold_dir: Path
    historical_json: Path
    historical_report: Path
    historical_lock: Path


class ProjectConfig(StrictSettings):
    project: ProjectSettings
    data: DataSettings
    artifacts: ArtifactSettings
    models: ModelSettings
    evaluation: EvaluationSettings
    risk_scoring: RiskScoringSettings
    reports: ReportSettings


def _read_yaml(config_path: str | Path) -> Mapping[str, Any]:
    resolved_path = resolve_path(config_path)
    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"Config file not found at '{resolved_path}'. Expected '{config_path}'."
        )
    try:
        payload = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(f"Failed to parse YAML config file at '{resolved_path}': {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Config file at '{resolved_path}' must contain a YAML object.")
    return payload


def load_project_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> ProjectConfig:
    """Parse and validate the complete authoritative configuration."""
    return ProjectConfig.model_validate(_read_yaml(config_path))


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Compatibility dictionary produced only after strict typed validation."""
    return load_project_config(config_path).model_dump(mode="python")


def get_config_value(
    config: Mapping[str, Any],
    dotted_key: str,
    default: Any = None,
) -> Any:
    """Retrieve a value from a validated configuration dictionary."""
    current: Any = config
    for key in dotted_key.split("."):
        if isinstance(current, Mapping) and key in current:
            current = current[key]
        else:
            return default
    return current
