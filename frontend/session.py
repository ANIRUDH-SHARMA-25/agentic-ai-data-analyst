"""Small session transitions shared by Streamlit and deterministic tests."""

from hashlib import sha256
from typing import Any, MutableMapping

from frontend.api_client import APIClient, APIClientError
from frontend.charts import build_chart

MAX_HISTORY = 10


def initialize_session(state: MutableMapping[str, Any]) -> None:
    defaults = {"dataset_id": None, "dataset_info": None, "upload_fingerprint": None,
                "conversation_id": None, "conversation_expired": False, "dataset_name": None,
                "dataset_size_bytes": 0, "dataset_expired": False}
    for key, value in defaults.items():
        state.setdefault(key, value)
    state.setdefault("history", [])


def clear_dataset(state: MutableMapping[str, Any]) -> None:
    for key in ("dataset_id", "dataset_info", "upload_fingerprint", "dataset_name"):
        state[key] = None
    state["dataset_size_bytes"] = 0
    state["dataset_expired"] = False
    state["history"] = []
    state["conversation_id"] = None
    state["conversation_expired"] = False


def reset_conversation(state: MutableMapping[str, Any], api: APIClient) -> None:
    if state["conversation_id"]:
        try:
            api.reset_conversation(state["dataset_id"], state["conversation_id"])
        except APIClientError as exc:
            if exc.status_code not in (404, 410):
                raise
    state["conversation_id"] = None
    state["conversation_expired"] = False
    state["history"] = []


def load_dataset(state: MutableMapping[str, Any], api: APIClient, filename: str, payload: bytes) -> bool:
    """Upload on explicit action only; retry pending inspection without reupload."""
    fingerprint = sha256(filename.encode("utf-8") + b"\x00" + payload).hexdigest()
    same_dataset = fingerprint == state["upload_fingerprint"] and state["dataset_id"] and not state["dataset_expired"]
    if same_dataset and state["dataset_info"] is not None:
        return False
    if not same_dataset:
        reset_conversation(state, api)
        clear_dataset(state)
        uploaded = api.upload(filename, payload)
        state["dataset_id"] = uploaded["dataset_id"]
        state["upload_fingerprint"] = fingerprint
        state["dataset_name"] = filename
        state["dataset_size_bytes"] = len(payload)
    try:
        state["dataset_info"] = api.inspect(state["dataset_id"])
    except APIClientError as exc:
        if exc.status_code == 404:
            state["dataset_expired"] = True
            state["conversation_id"] = None
        raise
    return True


def refresh_dataset(state: MutableMapping[str, Any], api: APIClient) -> None:
    try:
        state["dataset_info"] = api.inspect(state["dataset_id"])
    except APIClientError as exc:
        if exc.status_code == 404:
            state["dataset_expired"] = True
            state["conversation_id"] = None
        raise


def submit_question(state: MutableMapping[str, Any], api: APIClient, question: str) -> None:
    entry = {"question": question, "response": None, "error": None, "chart_kind": None}
    try:
        if state["conversation_id"]:
            response = api.analyze(state["dataset_id"], question, conversation_id=state["conversation_id"])
        else:
            response = api.analyze(state["dataset_id"], question)
        state["conversation_id"] = response.get("conversation_id")
        state["conversation_expired"] = False
        entry["response"] = response
        entry["chart_kind"] = build_chart(response["columns"], response["rows"]).kind
    except APIClientError as exc:
        entry["error"] = str(exc)
        if exc.status_code == 404:
            state["dataset_expired"] = True
            state["conversation_id"] = None
        if exc.status_code == 410:
            state["conversation_expired"] = True
        if exc.kind == "conversation_mismatch":
            state["conversation_id"] = None
            state["conversation_expired"] = True
    state["history"] = (state["history"] + [entry])[-MAX_HISTORY:]
