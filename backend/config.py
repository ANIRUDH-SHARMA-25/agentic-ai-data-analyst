"""Small, explicit backend configuration; .env files are not loaded automatically."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class APISettings:
    max_upload_bytes: int = 5 * 1024 * 1024
    dataset_ttl_seconds: int = 30 * 60
    max_active_datasets: int = 20
    temporary_directory: Path = Path(__file__).resolve().parents[1] / ".tmp" / "uploads"

    def __post_init__(self) -> None:
        for name in ("max_upload_bytes", "dataset_ttl_seconds", "max_active_datasets"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")

    @classmethod
    def from_environment(cls) -> "APISettings":
        return cls(
            max_upload_bytes=int(os.environ.get("UPLOAD_MAX_BYTES", 5 * 1024 * 1024)),
            dataset_ttl_seconds=int(os.environ.get("DATASET_TTL_SECONDS", 1800)),
            max_active_datasets=int(os.environ.get("MAX_ACTIVE_DATASETS", 20)),
        )
