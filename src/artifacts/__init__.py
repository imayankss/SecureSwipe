"""Versioned, integrity-checked local model artifacts."""

from src.artifacts.bundle import (
    BUNDLE_FORMAT_VERSION,
    ModelBundle,
    load_model_bundle,
    load_verified_joblib,
    save_model_bundle,
    write_checksum_sidecar,
)

__all__ = [
    "BUNDLE_FORMAT_VERSION",
    "ModelBundle",
    "load_model_bundle",
    "load_verified_joblib",
    "save_model_bundle",
    "write_checksum_sidecar",
]
