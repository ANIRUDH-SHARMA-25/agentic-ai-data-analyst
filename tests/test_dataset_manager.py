from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pandas as pd
import pytest

from backend.config import APISettings
from backend.data.csv_processing import DatasetError, load_csv_bytes
from backend.data.dataset_manager import DatasetCapacityError, DatasetManager, DatasetNotFoundError


def test_snapshot_and_returned_copy(retail_frame):
    manager = DatasetManager()
    dataset_id = manager.add(retail_frame)
    retail_frame.loc[0, "revenue"] = 999
    retrieved = manager.get(dataset_id)
    assert retrieved["revenue"].sum() == 530
    retrieved.loc[0, "revenue"] = -100
    assert manager.get(dataset_id)["revenue"].sum() == 530
    assert manager.uploaded_at(dataset_id).utcoffset().total_seconds() == 0


def test_lazy_cleanup_on_add(retail_frame):
    now = [0.0]
    manager = DatasetManager(ttl_seconds=10, max_datasets=1, clock=lambda: now[0])
    first = manager.add(retail_frame)
    now[0] = 10
    second = manager.add(retail_frame)
    assert first != second
    with pytest.raises(DatasetNotFoundError):
        manager.get(first)
    assert len(manager.get(second)) == 12


def test_access_only_refreshes_selected_dataset(retail_frame):
    now = [0.0]
    manager = DatasetManager(ttl_seconds=10, clock=lambda: now[0])
    first = manager.add(retail_frame)
    second = manager.add(retail_frame)
    now[0] = 9
    manager.get(first)
    now[0] = 10
    with pytest.raises(DatasetNotFoundError):
        manager.get(second)
    assert len(manager.get(first)) == 12


def test_invalid_dataset_does_not_consume_capacity(retail_frame):
    manager = DatasetManager(max_datasets=1)
    with pytest.raises(DatasetError):
        manager.add(pd.DataFrame())
    manager.add(retail_frame)
    with pytest.raises(DatasetCapacityError):
        manager.add(retail_frame)


def test_concurrent_add_respects_capacity(retail_frame):
    manager = DatasetManager(max_datasets=2)

    def attempt(_):
        try:
            return manager.add(retail_frame)
        except DatasetCapacityError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(10)))
    ids = [value for value in results if value is not None]
    assert len(ids) == len(set(ids)) == 2


def test_unknown_upload_time():
    with pytest.raises(DatasetNotFoundError):
        DatasetManager().uploaded_at(uuid4())


@pytest.mark.parametrize("kwargs", [{"ttl_seconds": 0}, {"max_datasets": -1}, {"ttl_seconds": True}])
def test_invalid_manager_configuration(kwargs):
    with pytest.raises(ValueError):
        DatasetManager(**kwargs)


@pytest.mark.parametrize("kwargs", [{"max_upload_bytes": 0}, {"dataset_ttl_seconds": True}, {"max_active_datasets": -1}])
def test_invalid_api_configuration(kwargs):
    with pytest.raises(ValueError):
        APISettings(**kwargs)


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "100")
    monkeypatch.setenv("DATASET_TTL_SECONDS", "60")
    monkeypatch.setenv("MAX_ACTIVE_DATASETS", "3")
    settings = APISettings.from_environment()
    assert (settings.max_upload_bytes, settings.dataset_ttl_seconds, settings.max_active_datasets) == (100, 60, 3)
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "invalid")
    with pytest.raises(ValueError):
        APISettings.from_environment()


def test_bytes_csv_loader():
    assert load_csv_bytes(b"a\n1\n", filename="test.csv")["a"].iloc[0] == 1
    with pytest.raises(DatasetError, match="Only .csv"):
        load_csv_bytes(b"a\n1\n", filename="test.txt")
    with pytest.raises(DatasetError, match="size limit"):
        load_csv_bytes(b"a\n1\n", filename="test.csv", max_bytes=3)
    with pytest.raises(DatasetError, match="positive integer"):
        load_csv_bytes(b"a\n1\n", filename="test.csv", max_bytes=0)
