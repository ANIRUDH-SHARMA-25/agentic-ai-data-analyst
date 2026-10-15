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
        assert body["contents"][0]["parts"] == [{"text":"Reply with OK."}]
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


@pytest.mark.parametrize("content,finish,category,visible", [
    ("OK", "STOP", "success", True),
    ("  OK\n", "STOP", "success", True),
    ("OK.", "STOP", "expected_text_format_variation", True),
    (["O", "K"], "STOP", "success", True),
    ([{"type":"text","text":"OK"}], "STOP", "success", True),
    ([{"type":"thinking","thinking":"private"},{"type":"text","text":"OK"}], "STOP", "success", True),
    ([{"type":"text","text":"private","thought":True}], "STOP", "empty_text", False),
    ("", "STOP", "empty_text", False),
    ("", "MAX_TOKENS", "output_truncated", False),
    ("OK", "MAX_TOKENS", "output_truncated", True),
    ([{"type":"image","data":"private"}], "STOP", "unsupported_content", False),
    ("A different answer", "STOP", "unexpected_text", True),
])
def test_safe_reply_classification(content, finish, category, visible):
    from langchain_core.messages import AIMessage
    from evaluations.plain_gemini_diagnostic import summarize_reply
    summary = summarize_reply(AIMessage(content=content, response_metadata={"finish_reason":finish, "private":"never copy"}))
    assert summary["category"] == category
    assert summary["has_visible_text"] is visible
    assert summary["finish_reason"] == finish
    assert "private" not in json.dumps(summary)
    assert "A different answer" not in json.dumps(summary)


@pytest.mark.parametrize("model_version,parts,finish,expected", [
    ("gemini-3.6-flash", [{"text":"OK"}], "STOP", "success"),
    ("gemini-3.6-flash", [{"text":"OK."}], "STOP", "expected_text_format_variation"),
    ("gemini-3.6-flash", [], "MAX_TOKENS", "output_truncated"),
    ("gemini-3.6-flash", [], "STOP", "empty_text"),
    ("gemini-3.6-flash", [{"text":"private thoughts","thought":True}], "MAX_TOKENS", "output_truncated"),
])
def test_installed_sdk_candidate_text_and_finish(model_version, parts, finish, expected):
    from google.genai.types import GenerateContentResponse
    from langchain_google_genai.chat_models import _response_to_result
    from evaluations.plain_gemini_diagnostic import summarize_reply
    raw = GenerateContentResponse.model_validate({"modelVersion":model_version,
        "candidates":[{"content":{"role":"model","parts":parts},"finishReason":finish}],
        "usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":1,"thoughtsTokenCount":255,"totalTokenCount":261}})
    result = _response_to_result(raw)
    generation = result.generations[0]
    # BaseChatModel adds the generation_info when creating the returned AIMessage.
    message = generation.message.model_copy(update={"response_metadata":{**generation.message.response_metadata, **(generation.generation_info or {})}})
    summary = summarize_reply(message)
    assert summary["category"] == expected
    assert summary["finish_reason"] == finish
    assert summary["reasoning_tokens"] == 255
    assert summary["output_tokens"] == 256
    assert "private thoughts" not in json.dumps(summary)


def test_safe_reply_metadata_allowlist():
    from langchain_core.messages import AIMessage
    from evaluations.plain_gemini_diagnostic import summarize_reply
    message = AIMessage(content="OK", response_metadata={"finish_reason":"private"})
    summary = summarize_reply(message)
    assert summary["finish_reason"] is None and "private" not in json.dumps(summary)
