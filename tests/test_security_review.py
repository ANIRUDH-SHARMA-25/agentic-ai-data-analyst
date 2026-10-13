"""Phase 8 regressions for request allocation and untrusted UI output."""
import pytest
from fastapi.testclient import TestClient
from backend.config import APISettings
from backend.main import create_app
from tests.test_frontend import app, button


@pytest.mark.parametrize("declared_length", [None, "1", "40000"])
def test_analysis_body_rejected_before_json_or_model(tmp_path, declared_length):
    class ForbiddenAnalyzer:
        def analyze(self, *args, **kwargs):
            pytest.fail("Oversized body must not reach analysis")
    headers = {"content-type": "application/json"}
    if declared_length is not None:
        headers["content-length"] = declared_length
    body = b'{"question":"' + b'x' * 40000 + b'"}'
    with TestClient(create_app(APISettings(temporary_directory=tmp_path / "uploads"), analyzer=ForbiddenAnalyzer())) as client:
        response = client.post("/analyze", content=iter([body[:100], body[100:]]), headers=headers)
    assert response.status_code == 413
    assert response.json() == {"detail": "Analysis request exceeds the size limit."}


def test_analysis_invalid_length_rejected(tmp_path):
    with TestClient(create_app(APISettings(temporary_directory=tmp_path / "uploads"))) as client:
        response = client.post("/analyze", content=b'{}', headers={"content-length":"bad"})
    assert response.status_code == 400


def test_chat_content_does_not_create_markdown_images(app):
    at, api = app
    button(at, "Try the retail sample").click().run()
    question = 'Explain ![question](https://example.invalid/collect?data=synthetic)'
    answer = '![answer](https://example.invalid/collect?data=synthetic) <img src="https://example.invalid/x">'
    api.analyze.return_value = {**api.analyze.return_value, "answer": answer}
    at.chat_input[0].set_value(question).run()
    assert not at.exception
    assert question in [item.value for item in at.text]
    assert answer in [item.value for item in at.text]
    assert not any("example.invalid" in item.value for item in at.markdown)
    assert len(at.get("plotly_chart")) == 1


def test_frontend_analysis_size_error_is_not_an_upload_error():
    import httpx
    from uuid import uuid4
    from frontend.api_client import APIClient, APIClientError
    from frontend.config import FrontendSettings
    api = APIClient(FrontendSettings(), transport=httpx.MockTransport(
        lambda request: httpx.Response(413, json={"detail": "Analysis request exceeds the size limit."})))
    with pytest.raises(APIClientError, match="analysis request"):
        api.analyze(str(uuid4()), "Explain revenue")
