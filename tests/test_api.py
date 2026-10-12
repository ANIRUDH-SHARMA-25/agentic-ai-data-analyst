import json
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.config import APISettings
from backend.data.dataset_manager import DatasetManager, DatasetNotFoundError
from backend.main import create_app


@pytest.fixture
def settings(tmp_path):
    return APISettings(temporary_directory=tmp_path / "uploads")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as session:
        yield session


def upload(client, data=b"product,revenue\na,10\nb,20\n", name="sales.csv", **kwargs):
    return client.post("/upload", files={"file": (name, data, "text/csv")}, **kwargs)


def test_health(client):
    assert client.get("/health").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_and_retrieve_retail(client):
    sample = Path(__file__).resolve().parents[1] / "data/sample/retail_sales.csv"
    response = upload(client, sample.read_bytes(), "retail_sales.csv")
    assert response.status_code == 201
    result = response.json()
    assert UUID(result["dataset_id"]).version == 4
    assert result["row_count"] == 12
    assert result["column_count"] == 6
    assert result["columns"] == ["date", "product", "category", "quantity", "unit_price", "revenue"]
    assert result["dtypes"]["quantity"] == "int64"
    assert len(result["preview"]) == 5
    information = client.get(f'/dataset/{result["dataset_id"]}')
    assert information.status_code == 200
    summary = information.json()
    assert all(summary[key] == value for key, value in result.items())
    assert summary["missing_values"] == {column: 0 for column in result["columns"]}
    assert summary["statistics"]["revenue"]["mean"] == pytest.approx(530 / 12)


@pytest.mark.parametrize(("data", "name", "status"), [
    (b"a\n1\n", "sales.txt", 415),
    (b"a\n1\n", "sales.xlsx", 415),
    (b"a\n1\n", "../sales.csv", 400),
    (b"a\n1\n", "folder/sales.csv", 400),
    (b"a\n1\n", "D:evil.csv", 400),
    (b"", "sales.csv", 400),
    (b" \n\t", "sales.csv", 400),
    (b"a,b\n", "sales.csv", 400),
    (b"a,b\n1,2,3\n", "sales.csv", 400),
    (b"a,b\n1\n", "sales.csv", 400),
    (b'a,b\n1,"broken\n', "sales.csv", 400),
    (b"a,a\n1,2\n", "sales.csv", 400),
    (b"a,\n1,2\n", "sales.csv", 400),
    (b"a\n\xff\n", "sales.csv", 400),
    (b"a\n\x00\n", "sales.csv", 400),
])
def test_invalid_uploads(client, data, name, status):
    response = upload(client, data, name)
    assert response.status_code == status
    assert isinstance(response.json()["detail"], str)


def test_filename_validation(client):
    # Multipart libraries normalize Windows path names; traversal with / stays explicit.
    response = upload(client, name="x" * 256 + ".csv")
    assert response.status_code == 400


def test_extension_case_and_mime_not_trusted(client):
    response = client.post("/upload", files={"file": ("DATA.CSV", b"a\n1\n", "application/octet-stream")})
    assert response.status_code == 201
    response = client.post("/upload", files={"file": ("DATA.CSV", b"a\n\xff\n", "text/csv")})
    assert response.status_code == 400


def test_missing_file_and_invalid_id(client):
    assert client.post("/upload").status_code == 422
    assert client.get("/dataset/not-a-uuid").status_code == 422
    response = client.get(f"/dataset/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset not found or expired."}


def test_file_size_boundary(settings):
    with TestClient(create_app(replace(settings, max_upload_bytes=8))) as client:
        assert upload(client, b"a\n12345\n").status_code == 201
        response = upload(client, b"a\n123456\n")
        assert response.status_code == 413
        assert "size limit" in response.json()["detail"]
        assert upload(client, b"a\n" + b"x" * 70000).status_code == 413


@pytest.mark.parametrize("content_length", [None, "1"])
def test_chunked_or_inaccurate_content_length(settings, content_length):
    boundary = "test-boundary"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n'
            'Content-Type: text/csv\r\n\r\n').encode() + b"a\n" + b"x" * 70000
    body += f"\r\n--{boundary}--\r\n".encode()
    headers = {"content-type": f"multipart/form-data; boundary={boundary}"}
    if content_length is not None:
        headers["content-length"] = content_length
    with TestClient(create_app(replace(settings, max_upload_bytes=8))) as client:
        response = client.post("/upload", content=iter([body[:100], body[100:]]), headers=headers)
        assert response.status_code == 413
        assert "size limit" in response.json()["detail"]


def test_invalid_content_length(client):
    response = client.post("/upload", content=b"abc", headers={"content-length": "bad"})
    assert response.status_code == 400


def test_expiration_capacity_and_access_refresh(settings):
    now = [0.0]
    manager = DatasetManager(ttl_seconds=10, max_datasets=1, clock=lambda: now[0])
    with TestClient(create_app(settings, manager=manager)) as client:
        first = upload(client).json()["dataset_id"]
        response = upload(client)
        assert response.status_code == 503
        now[0] = 9
        assert client.get(f"/dataset/{first}").status_code == 200
        now[0] = 18
        assert client.get(f"/dataset/{first}").status_code == 200
        now[0] = 28
        assert client.get(f"/dataset/{first}").status_code == 404
        assert upload(client).status_code == 201


def test_multiple_dataset_isolation(client):
    first = upload(client, b"name,amount\nfirst,1\n").json()["dataset_id"]
    second = upload(client, b"name,amount\nsecond,99\n").json()["dataset_id"]
    assert first != second
    assert client.get(f"/dataset/{first}").json()["preview"] == [{"name": "first", "amount": 1}]
    assert client.get(f"/dataset/{second}").json()["preview"] == [{"name": "second", "amount": 99}]


def test_missing_and_nonfinite_upload(client):
    response = upload(client, b"name,amount\na,inf\nb,\nc,-inf\nd,2\n")
    assert response.status_code == 201
    summary = client.get(f'/dataset/{response.json()["dataset_id"]}').json()
    assert summary["missing_values"]["amount"] == 1
    assert [row["amount"] for row in summary["preview"]] == [None, None, None, 2.0]
    assert summary["statistics"]["amount"]["mean"] == 2.0
    json.dumps(summary, allow_nan=False)


def test_timestamps_and_numpy_pandas_scalars(settings):
    manager = DatasetManager()
    dataset_id = manager.add(pd.DataFrame({
        "when": pd.to_datetime(["2026-01-01", None]),
        "number": np.array([1, 2], dtype=np.int64),
        "nullable": pd.Series([pd.NA, 3], dtype="Int64"),
    }))
    with TestClient(create_app(settings, manager=manager)) as client:
        response = client.get(f"/dataset/{dataset_id}")
        assert response.status_code == 200
        summary = response.json()
        assert summary["preview"][0]["when"].startswith("2026-01-01T00:00:00")
        assert summary["preview"][1]["when"] is None
        assert summary["preview"][0]["nullable"] is None
        assert summary["preview"][0]["number"] == 1
        json.dumps(summary, allow_nan=False)


def test_multipart_spool_is_temporary_on_d(settings, monkeypatch):
    locations = []
    original = tempfile.TemporaryFile

    def record_tempfile(*args, **kwargs):
        locations.append(Path(kwargs.get("dir") or tempfile.gettempdir()))
        return original(*args, **kwargs)

    monkeypatch.setattr(tempfile, "TemporaryFile", record_tempfile)
    before_directory = tempfile.tempdir
    with TestClient(create_app(settings)) as client:
        # One large cell under csv.reader's field-size limit, repeated to trigger spooling.
        payload = b"value\n" + (b"x" * 100000 + b"\n") * 11
        assert upload(client, payload).status_code == 201
        assert locations
        assert all(path == settings.temporary_directory for path in locations)
        assert not list(settings.temporary_directory.iterdir())
    assert tempfile.tempdir == before_directory


def test_shutdown_discards_sessions(settings):
    manager = DatasetManager()
    with TestClient(create_app(settings, manager=manager)) as client:
        dataset_id = UUID(upload(client).json()["dataset_id"])
    with pytest.raises(DatasetNotFoundError):
        manager.get(dataset_id)


def test_openapi_and_scope(client):
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {"/health", "/upload", "/dataset/{dataset_id}"}
    assert "multipart/form-data" in schema["paths"]["/upload"]["post"]["requestBody"]["content"]
    assert "DatasetResponse" in schema["components"]["schemas"]
    assert client.get("/docs").status_code == 200
    assert client.post("/analyze").status_code == 404
