import json
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from backend.agent.analyst import DataAnalysisAgent
from backend.config import APISettings
from backend.data.dataset_manager import DatasetManager
from backend.data.safe_sql import SQLTimeoutError
from backend.main import create_app
from tests.fake_models import ScriptedModel, call_tool
from tests.test_agent import TOP_SQL, grounded_final, provider_error


def settings(tmp_path):
    return APISettings(temporary_directory=tmp_path / "uploads")


def analyzer_for(responses):
    return DataAnalysisAgent(model_factory=lambda configuration: ScriptedModel(responses=responses))


def upload_sample(client):
    path = Path(__file__).resolve().parents[1] / "data/sample/retail_sales.csv"
    response = client.post("/upload", files={"file": (path.name, path.read_bytes(), "text/csv")})
    assert response.status_code == 201
    return response.json()["dataset_id"]


def test_mocked_upload_analyze_result_workflow(tmp_path):
    analyzer = analyzer_for([call_tool("inspect_dataset"), call_tool("execute_sql", {"query": TOP_SQL}), grounded_final])
    with TestClient(create_app(settings(tmp_path), analyzer=analyzer)) as client:
        dataset_id = upload_sample(client)
        response = client.post("/analyze", json={"dataset_id": dataset_id, "question": "Which category generated the highest total revenue?"})
        assert response.status_code == 200
        result = response.json()
        assert UUID(result.pop("conversation_id"))
        assert result == {
            "answer": "Electronics generated the highest total revenue: 260.",
            "sql": TOP_SQL, "columns": ["category", "total"], "rows": [["Electronics", 260.0]],
            "row_count": 1, "tools_used": ["inspect_dataset", "execute_sql"],
        }
        json.dumps(response.json(), allow_nan=False)


@pytest.mark.parametrize("question", ["", "   ", "???", "x" * 2001, "bad\x00question", None, 123, ["hello"]])
def test_question_validation(tmp_path, question):
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post("/analyze", json={"dataset_id": str(uuid4()), "question": question})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)


def test_id_validation_unknown_dataset_and_extra_request_fields(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.post("/analyze", json={"dataset_id": "invalid", "question": "Total?"}).status_code == 422
        assert client.post("/analyze", json={"dataset_id": str(uuid4()), "question": "Total?"}).status_code == 404
        assert client.post("/analyze", json={"dataset_id": str(uuid4()), "question": "Total?", "sql": "DROP TABLE dataset"}).status_code == 422


def test_expired_analysis_dataset(tmp_path):
    now = [0.0]
    manager = DatasetManager(ttl_seconds=10, clock=lambda: now[0])
    with TestClient(create_app(settings(tmp_path), manager=manager)) as client:
        dataset_id = upload_sample(client)
        now[0] = 10
        response = client.post("/analyze", json={"dataset_id": dataset_id, "question": "Total revenue?"})
        assert response.status_code == 404
        assert response.json() == {"detail": "Dataset not found or expired."}


def test_missing_key_preserves_other_apis(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/health").status_code == 200
        dataset_id = upload_sample(client)
        assert client.get(f"/dataset/{dataset_id}").status_code == 200
        response = client.post("/analyze", json={"dataset_id": dataset_id, "question": "Total revenue?"})
        assert response.status_code == 503
        assert "OPENAI_API_KEY" in response.json()["detail"]
        assert "answer" not in response.json()


@pytest.mark.parametrize("kind", ["timeout", "connection", "auth", "permission", "rate"])
def test_provider_errors_http_status_and_no_sensitive_details(tmp_path, kind):
    error, expected = provider_error(kind)
    with TestClient(create_app(settings(tmp_path), analyzer=analyzer_for([error]))) as client:
        dataset_id = upload_sample(client)
        response = client.post("/analyze", json={"dataset_id": dataset_id, "question": "Total revenue?"})
        assert response.status_code == expected
        assert "private runtime details" not in response.text
        assert "Traceback" not in response.text
        assert set(response.json()) == {"detail"}


def test_analysis_dataset_isolation(tmp_path):
    def final(messages):
        evidence = json.loads([message for message in messages if isinstance(message, ToolMessage)][-1].content)
        return AIMessage(content=f"The computed total is {evidence['rows'][0][0]:g}.")
    analyzer = analyzer_for([call_tool("inspect_dataset"), call_tool("execute_sql", {"query": "SELECT SUM(revenue) AS total FROM dataset"}), final])
    with TestClient(create_app(settings(tmp_path), analyzer=analyzer)) as client:
        ids = []
        for value in [1, 99]:
            uploaded = client.post("/upload", files={"file": ("a.csv", f"revenue\n{value}\n".encode(), "text/csv")})
            ids.append(uploaded.json()["dataset_id"])
        for dataset_id, expected in zip(ids, [1, 99]):
            response = client.post("/analyze", json={"dataset_id": dataset_id, "question": "Total revenue?"})
            assert response.status_code == 200
            assert response.json()["rows"] == [[expected]]
            assert str(expected) in response.json()["answer"]


def test_sql_rejection_and_retry_never_success(tmp_path):
    analyzer = analyzer_for([
        call_tool("inspect_dataset"), call_tool("execute_sql", {"query": "DROP TABLE dataset"}),
        call_tool("execute_sql", {"query": "SELECT * FROM read_csv('secret.csv')"}),
        AIMessage(content="Fake total 999"),
    ])
    with TestClient(create_app(settings(tmp_path), analyzer=analyzer)) as client:
        dataset_id = upload_sample(client)
        response = client.post("/analyze", json={"dataset_id": dataset_id, "question": "Total?"})
        assert response.status_code == 422
        assert "answer" not in response.json()


def test_no_sql_for_unsupported_question(tmp_path):
    analyzer = analyzer_for([call_tool("inspect_dataset"), AIMessage(content="This dataset does not contain weather observations or forecasts.")])
    with TestClient(create_app(settings(tmp_path), analyzer=analyzer)) as client:
        response = client.post("/analyze", json={"dataset_id": upload_sample(client), "question": "Predict weather"})
        assert response.status_code == 200
        assert response.json()["sql"] is None
        assert response.json()["rows"] == []


def test_analysis_json_nonfinite_and_timestamp_results(tmp_path):
    manager = DatasetManager()
    dataset_id = manager.add(pd.DataFrame({"n": [float("inf"), None], "when": pd.to_datetime(["2026-01-01", None])}))
    analyzer = analyzer_for([call_tool("inspect_dataset"), call_tool("execute_sql", {"query": "SELECT * FROM dataset"}), AIMessage(content="The returned data includes missing and nonfinite values.")])
    with TestClient(create_app(settings(tmp_path), manager=manager, analyzer=analyzer)) as client:
        response = client.post("/analyze", json={"dataset_id": str(dataset_id), "question": "Show data"})
        assert response.status_code == 200
        rows = response.json()["rows"]
        assert rows[0][0] is None and rows[0][1].startswith("2026-01-01T")
        assert rows[1] == [None, None]
        json.dumps(response.json(), allow_nan=False)


def test_sql_timeout_http_error(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise SQLTimeoutError("SQL query exceeded its execution time limit.")
    monkeypatch.setattr("backend.agent.analyst.execute_safe_sql", timeout)
    analyzer = analyzer_for([call_tool("inspect_dataset"), call_tool("execute_sql", {"query": TOP_SQL})])
    with TestClient(create_app(settings(tmp_path), analyzer=analyzer)) as client:
        response = client.post("/analyze", json={"dataset_id": upload_sample(client), "question": "Total?"})
        assert response.status_code == 504


def test_invalid_provider_configuration_is_lazy(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "not-a-number")
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/analyze", json={"dataset_id": upload_sample(client), "question": "Total?"})
        assert response.status_code == 503
        assert "configuration" in response.json()["detail"]
