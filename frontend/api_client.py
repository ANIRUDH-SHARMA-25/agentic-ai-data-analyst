"""Small HTTPX client; no backend objects, automatic retries, or provider keys."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from frontend.config import FrontendSettings


class APIClientError(RuntimeError):
    """A user-readable error with an optional backend HTTP status."""

    def __init__(self, message: str, status_code: int | None = None, *, kind: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind


def _invalid_response() -> APIClientError:
    return APIClientError("The backend returned an unexpected response. Check its version and try again.")


def _validate_dataset(data: dict[str, Any], *, inspected: bool) -> dict[str, Any]:
    try:
        UUID(data["dataset_id"])
        if (type(data["row_count"]) is not int or data["row_count"] < 1
                or type(data["column_count"]) is not int or data["column_count"] < 1
                or not isinstance(data["columns"], list)
                or not all(isinstance(name, str) for name in data["columns"])
                or len(data["columns"]) != data["column_count"]
                or not isinstance(data["dtypes"], dict)
                or not all(isinstance(value, str) for value in data["dtypes"].values())
                or not isinstance(data["preview"], list) or len(data["preview"]) > 20
                or not all(isinstance(row, dict) for row in data["preview"])):
            raise _invalid_response()
        if inspected and (not isinstance(data["statistics"], dict)
                or not all(isinstance(value, dict) for value in data["statistics"].values())
                or not isinstance(data["missing_values"], dict)
                or not all(type(value) is int and value >= 0 for value in data["missing_values"].values())):
            raise _invalid_response()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _invalid_response() from exc
    return data


def _validate_analysis(data: dict[str, Any]) -> dict[str, Any]:
    try:
        if data.get("conversation_id") is not None:
            UUID(data["conversation_id"])
        if (not isinstance(data["answer"], str) or not data["answer"].strip() or len(data["answer"]) > 16000
                or (data["sql"] is not None and not isinstance(data["sql"], str))
                or not isinstance(data["columns"], list) or len(data["columns"]) > 1000
                or not all(isinstance(name, str) for name in data["columns"])
                or not isinstance(data["rows"], list) or len(data["rows"]) > 1000
                or not all(isinstance(row, list) and len(row) == len(data["columns"]) for row in data["rows"])
                or not all(value is None or type(value) in (str, int, float, bool) for row in data["rows"] for value in row)
                or type(data["row_count"]) is not int or data["row_count"] != len(data["rows"])
                or not isinstance(data["tools_used"], list) or len(data["tools_used"]) > 10
                or not all(isinstance(name, str) for name in data["tools_used"])):
            raise _invalid_response()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _invalid_response() from exc
    return data


class APIClient:
    def __init__(self, settings: FrontendSettings, *, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    def _request(self, method: str, path: str, *, analysis: bool = False, **kwargs) -> dict[str, Any]:
        read_timeout = (self.settings.analysis_timeout_seconds if analysis
                        else self.settings.request_timeout_seconds)
        timeout = httpx.Timeout(read_timeout, connect=5.0, pool=5.0)
        try:
            # HTTPX defaults to zero retries. Never replay a paid /analyze request.
            with httpx.Client(timeout=timeout, transport=self.transport, trust_env=False) as client:
                response = client.request(method, self.settings.backend_url.rstrip("/") + path, **kwargs)
        except httpx.TimeoutException as exc:
            raise APIClientError("The request timed out. It was not retried; analysis may still be running on the backend.") from exc
        except httpx.RequestError as exc:
            raise APIClientError("Cannot reach the backend. Start the local backend and check the configured address.") from exc
        if response.status_code >= 300:
            try:
                detail = response.json().get("detail", "")
            except (ValueError, AttributeError):
                detail = ""
            messages = {
                400: "The CSV or request is invalid. Check the file contents and try again.",
                404: "This dataset has expired or is no longer available. Upload the CSV again.",
                409: "This conversation is busy or belongs to another dataset. Wait for the active analysis or start a new conversation.",
                410: "This conversation has expired or was cleared. Start a new conversation; the dataset may still be available.",
                413: "The upload exceeds the backend size limit. Choose a smaller CSV.",
                415: "Only CSV files are supported.",
                422: "This question or analysis is unsupported. Try a simpler question using the dataset's columns.",
                429: "The AI provider is busy or rate-limited. Wait before submitting another question.",
                502: "The AI provider could not complete this analysis. No answer was substituted.",
                503: "The backend or AI provider is unavailable. Check its configuration and try again.",
                504: "The analysis exceeded its time limit. Try a simpler question.",
            }
            if response.status_code == 503 and isinstance(detail, str) and "OPENAI_API_KEY" in detail:
                message = "AI analysis is not configured. Set OPENAI_API_KEY in the backend terminal; upload and inspection still work."
            else:
                message = messages.get(response.status_code, "The backend could not complete the request.")
            kind = None
            if response.status_code == 409 and isinstance(detail, str) and detail.startswith("Conversation belongs to a different dataset"):
                kind = "conversation_mismatch"
                message = "This conversation belongs to another dataset. Start a new conversation for the selected dataset."
            raise APIClientError(message, response.status_code, kind=kind)
        if len(response.content) > 2 * 1024 * 1024:
            raise APIClientError("The backend response is too large for this frontend. Use a smaller dataset or result.")
        try:
            def invalid_constant(value):
                raise ValueError("Non-standard JSON constant")
            data = json.loads(response.content, parse_constant=invalid_constant)
        except (ValueError, UnicodeDecodeError) as exc:
            raise _invalid_response() from exc
        if not isinstance(data, dict):
            raise _invalid_response()
        return data

    @staticmethod
    def _dataset_id(value: str) -> str:
        try:
            return str(UUID(value))
        except (ValueError, TypeError, AttributeError) as exc:
            raise APIClientError("The dataset session is invalid. Upload the CSV again.") from exc

    def health(self) -> dict[str, Any]:
        data = self._request("GET", "/health")
        if data.get("status") != "ok":
            raise _invalid_response()
        return data

    def upload(self, filename: str, payload: bytes) -> dict[str, Any]:
        if Path(filename).suffix.lower() != ".csv":
            raise APIClientError("Choose a .csv file.")
        if not payload:
            raise APIClientError("The CSV is empty. Choose a file with a header and data rows.")
        if len(payload) > self.settings.max_upload_bytes:
            raise APIClientError("The CSV exceeds the configured upload limit.")
        return _validate_dataset(self._request("POST", "/upload", files={"file": (filename, payload, "text/csv")}), inspected=False)

    def inspect(self, dataset_id: str) -> dict[str, Any]:
        dataset_id = self._dataset_id(dataset_id)
        result = _validate_dataset(self._request("GET", f"/dataset/{dataset_id}"), inspected=True)
        if result["dataset_id"] != dataset_id:
            raise _invalid_response()
        return result

    def analyze(self, dataset_id: str, question: str, conversation_id: str | None = None) -> dict[str, Any]:
        dataset_id = self._dataset_id(dataset_id)
        question = question.strip()
        if not question or len(question) > 2000 or not any(character.isalnum() for character in question):
            raise APIClientError("Enter a meaningful question of at most 2,000 characters.")
        body = {"dataset_id": dataset_id, "question": question}
        if conversation_id is not None:
            try:
                body["conversation_id"] = str(UUID(conversation_id))
            except (ValueError, TypeError, AttributeError) as exc:
                raise APIClientError("The conversation session is invalid. Start a new conversation.", 410) from exc
        result = _validate_analysis(self._request("POST", "/analyze", analysis=True, json=body))
        if conversation_id is not None and result.get("conversation_id") != body["conversation_id"]:
            raise _invalid_response()
        return result

    def reset_conversation(self, dataset_id: str, conversation_id: str) -> None:
        try:
            conversation_id = str(UUID(conversation_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise APIClientError("The conversation session is invalid. Start a new conversation.", 410) from exc
        data = self._request("DELETE", f"/conversation/{conversation_id}",
                             params={"dataset_id": self._dataset_id(dataset_id)})
        if data.get("status") != "ok":
            raise _invalid_response()
