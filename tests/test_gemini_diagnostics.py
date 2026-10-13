"""Real SDK serialization against a sealed in-memory transport, never Google."""
import json
import httpx
import pytest
from google.genai.errors import APIError
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.agent.analyst import AnalysisError, DataAnalysisAgent
from backend.agent.config import AgentSettings
from backend.agent.diagnostics import provider_diagnostic
from evaluations.live_gemini import DiagnosticAgent

# Capture before the autouse fixture forbids provider calls. Re-enable only for
# clients constructed below with an explicit MockTransport (no socket transport).
SDK_GENERATE = ChatGoogleGenerativeAI._generate


def sealed_agent(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    def constructor(**kwargs):
        return ChatGoogleGenerativeAI(**kwargs, client_args={"transport": transport})
    monkeypatch.setattr("backend.agent.analyst.ChatGoogleGenerativeAI", constructor)
    def generate(self, *args, **kwargs):
        assert self.client._api_client._http_options.client_args["transport"] is transport
        return SDK_GENERATE(self, *args, **kwargs)
    monkeypatch.setattr(ChatGoogleGenerativeAI, "_generate", generate)
    return DiagnosticAgent(settings=AgentSettings(api_key="offline-fake-key", free_tier_confirmed=True))


def test_actual_agent_wire_and_signature_replay(monkeypatch, retail_frame):
    bodies = []
    def handler(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.path == "/v1beta/models/gemini-3.8-flash:generateContent"
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            part = {"functionCall": {"name": "inspect_dataset", "args": {}}, "thoughtSignature": "c2lnbmF0dXJl"}
        elif len(bodies) == 2:
            part = {"functionCall": {"name": "execute_sql", "args": {"query": "SELECT SUM(revenue) FROM dataset"}}, "thoughtSignature": "c2lnbmF0dXJl"}
        else:
            part = {"text": "Total revenue is 530."}
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [part]}, "finishReason": "STOP"}]})
    agent = sealed_agent(monkeypatch, handler)
    result = agent.analyze(retail_frame, "Synthetic offline total revenue test")
    assert result.rows == [[530]] and result.tools_used == ["inspect_dataset", "execute_sql"]
    assert len(bodies) == 3
    for body in bodies:
        config = body["generationConfig"]
        assert not {"temperature", "topP", "topK"} & config.keys()
        assert config["maxOutputTokens"] == 1200
        assert config["thinkingConfig"] == {"include_thoughts": False, "thinking_level": "LOW"}
        assert config["responseModalities"] == ["TEXT"]
        assert "serviceTier" not in body
        declarations = body["tools"][0]["functionDeclarations"]
        assert {d["name"] for d in declarations} == {"inspect_dataset", "get_statistics", "execute_sql"}
        sql = next(d for d in declarations if d["name"] == "execute_sql")
        assert sql["parameters"]["required"] == ["query"]
        assert sql["parameters"]["properties"]["query"]["type"] == "STRING"
    replay = bodies[1]["contents"]
    assert replay[-2]["parts"][0]["thoughtSignature"] == "c2lnbmF0dXJl"
    assert replay[-1]["parts"][0]["functionResponse"]["name"] == "inspect_dataset"


@pytest.mark.parametrize("code,status,category,backend", [
    (400,"INVALID_ARGUMENT","invalid_request_or_precondition",502),
    (400,"FAILED_PRECONDITION","failed_precondition",502),
    (401,"UNAUTHENTICATED","authentication",503),
    (403,"PERMISSION_DENIED","access_denied",503),
    (404,"NOT_FOUND","model_or_resource_not_found",503),
    (429,"RESOURCE_EXHAUSTED","quota_or_rate_limit",429),
    (500,"INTERNAL","service_error",502),
    (503,"UNAVAILABLE","service_unavailable",502),
    (504,"DEADLINE_EXCEEDED","timeout",504),
])
def test_real_sdk_error_mapping_no_retries(monkeypatch, retail_frame, code, status, category, backend):
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(code, json={"error": {"code": code, "status": status, "message": "secret-key prompt response-body private"}})
    agent = sealed_agent(monkeypatch, handler)
    with pytest.raises(AnalysisError) as caught:
        agent.analyze(retail_frame, "Synthetic offline test")
    assert count == 1
    assert caught.value.status_code == backend
    assert agent.last_provider_diagnostic == {"category": category, "upstream_http_status": code, "upstream_status": status}
    assert "private" not in json.dumps(agent.last_provider_diagnostic)
    assert "secret-key" not in str(caught.value)


def test_diagnostics_allowlist_causes_and_cycle():
    error = APIError(400, {"error": {"status": "secret-key private prompt", "message": "secret-key private prompt"}})
    wrapped = RuntimeError("private")
    outer = RuntimeError("private")
    outer.__cause__ = wrapped
    wrapped.__cause__ = error
    error.__cause__ = outer
    assert provider_diagnostic(outer) == {"category": "invalid_request_or_precondition", "upstream_http_status": 400, "upstream_status": None}
    error.code = "private"
    assert provider_diagnostic(outer)["upstream_http_status"] is None


def test_client_timeout_is_not_upstream_504():
    assert provider_diagnostic(httpx.ReadTimeout("private URL key prompt")) == {"category": "timeout", "upstream_http_status": None, "upstream_status": None}
