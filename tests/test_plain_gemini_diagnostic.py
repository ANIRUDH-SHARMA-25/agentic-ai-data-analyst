"""Single diagnostic constraints checked with a sealed offline SDK transport."""
import json
import httpx
import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.agent.analyst import create_gemini_model
from evaluations.plain_gemini_diagnostic import run_plain

SDK_GENERATE = ChatGoogleGenerativeAI._generate


def test_approval_precedes_configuration(tmp_path):
    with pytest.raises(ValueError, match="approval"):
        run_plain(output=tmp_path / "report.json")


@pytest.mark.parametrize("code", [200, 400, 429, 503])
def test_single_plain_request_offline(monkeypatch, tmp_path, code):
    seen = []
    def handler(request):
        body = json.loads(request.content)
        assert not {"tools", "toolConfig", "systemInstruction"} & body.keys()
        assert len(body["contents"]) == 1
        assert body["generationConfig"]["maxOutputTokens"] == 256
        seen.append(body)
        if code == 200:
            payload = {"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}, "finishReason": "STOP"}]}
        else:
            payload = {"error": {"code": code, "status": {400:"INVALID_ARGUMENT",429:"RESOURCE_EXHAUSTED",503:"UNAVAILABLE"}[code], "message":"private key prompt response"}}
        return httpx.Response(code, json=payload)
    transport = httpx.MockTransport(handler)
    def constructor(**kwargs):
        return ChatGoogleGenerativeAI(**kwargs, client_args={"transport": transport})
    monkeypatch.setattr("backend.agent.analyst.ChatGoogleGenerativeAI", constructor)
    def generate(self, *args, **kwargs):
        assert self.client._api_client._http_options.client_args["transport"] is transport
        return SDK_GENERATE(self, *args, **kwargs)
    monkeypatch.setattr(ChatGoogleGenerativeAI, "_generate", generate)
    monkeypatch.setenv("GOOGLE_API_KEY", "offline-fake-key")
    monkeypatch.setenv("GOOGLE_FREE_TIER_CONFIRMED", "true")
    output = tmp_path / "report.json"
    report = run_plain(approved=True, output=output, model_factory=create_gemini_model)
    assert len(seen) == report["generation_attempts"] == 1
    assert report["success"] == (code == 200)
    assert report["upstream_http_status"] == code
    assert "private" not in output.read_text() and "offline-fake-key" not in output.read_text()
    with pytest.raises(ValueError, match="already exists"):
        run_plain(approved=True, output=output)
    assert len(seen) == 1
