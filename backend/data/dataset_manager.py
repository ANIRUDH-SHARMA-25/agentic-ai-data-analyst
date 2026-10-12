"""Thread-safe, single-process dataset sessions with lazy inactivity expiration."""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Callable
from uuid import UUID, uuid4

import pandas as pd

from backend.data.csv_processing import validate_dataframe


class DatasetNotFoundError(LookupError):
    """The dataset is unknown or has expired."""


class DatasetCapacityError(RuntimeError):
    """All active dataset slots are occupied."""


@dataclass
class _DatasetEntry:
    frame: pd.DataFrame
    uploaded_at: datetime
    last_access: float


class DatasetManager:
    """Keep independent snapshots and return copies for future analysis tools.

    UUIDs select datasets; they are not user authentication. A monotonic clock
    measures inactivity so wall-clock adjustments cannot change expiration.
    """

    def __init__(
        self, *, ttl_seconds: int = 1800, max_datasets: int = 20,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        for name, value in (("ttl_seconds", ttl_seconds), ("max_datasets", max_datasets)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        self._ttl_seconds = ttl_seconds
        self._max_datasets = max_datasets
        self._clock = clock
        self._entries: dict[UUID, _DatasetEntry] = {}
        self._lock = Lock()

    def _cleanup(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items()
                   if now - entry.last_access >= self._ttl_seconds]
        for key in expired:
            del self._entries[key]

    def add(self, frame: pd.DataFrame) -> UUID:
        validate_dataframe(frame)
        with self._lock:
            now = self._clock()
            self._cleanup(now)
            if len(self._entries) >= self._max_datasets:
                raise DatasetCapacityError("Dataset capacity reached. Try again after a session expires.")
            dataset_id = uuid4()
            self._entries[dataset_id] = _DatasetEntry(
                frame.copy(deep=True), datetime.now(timezone.utc), now,
            )
            return dataset_id

    def get(self, dataset_id: UUID) -> pd.DataFrame:
        """Return a copy and refresh inactivity only for the selected dataset."""
        with self._lock:
            now = self._clock()
            self._cleanup(now)
            entry = self._entries.get(dataset_id)
            if entry is None:
                raise DatasetNotFoundError("Dataset not found or expired.")
            entry.last_access = now
            return entry.frame.copy(deep=True)

    def uploaded_at(self, dataset_id: UUID) -> datetime:
        """Read immutable upload time without extending the inactivity deadline."""
        with self._lock:
            self._cleanup(self._clock())
            entry = self._entries.get(dataset_id)
            if entry is None:
                raise DatasetNotFoundError("Dataset not found or expired.")
            return entry.uploaded_at

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
